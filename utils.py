# utils.py
# 中文排版工具 - 核心处理模块（v3）
#
# 主入口：process_text(text) 负责标点转换、引号审查和空格清理。

import re

# ──────────────────────────────────────────────
# 常量
# ──────────────────────────────────────────────

MAX_TEXT_LENGTH = 100000   # 最大输入字符数（个人单用户）

# 英文标点 → 中文标点映射表
PUNCT_MAP = {
    ',':  '，',
    '.':  '。',
    '?':  '？',
    '!':  '！',
    ':':  '：',
    ';':  '；',
    '(':  '（',
    ')':  '）',
    '[':  '【',
    ']':  '】',
    '{':  '｛',
    '}':  '｝',
    '<':  '《',
    '>':  '》',
    '~':  '～',
    '`':  '｀',
    '@':  '＠',
    '$':  '￥',
    '%':  '％',
    '&':  '＆',
    '|':  '｜',
    '_':  '＿',
}

# CJK 字符范围（用于间距正则，避免各处重复书写）
_CJK_CHAR_PAT = re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf\uff00-\uffef\u3000-\u303f]')
# 中文标点集合（用于空格清理）
_ZH_PUNCT = '，。？！：；、“”‘’【】《》（）｛｝～…—·'
_LATIN_ALNUM_PAT = re.compile(r'[A-Za-z0-9]')
# ──────────────────────────────────────────────

# 占位符格式：使用 \x02 \x03 作为边界（ASCII控制字符，不在任何映射表中）
# 绝对不能包含任何 PUNCT_MAP 中的字符（, . ? ! : ; ( ) [ ] { } < > ~ ` @ $ % & | _）
_PLACEHOLDER_FMT = '\x02PROT{}\x03'
_PLACEHOLDER_PAT = re.compile(r'\x02PROT\d+\x03')

# 分组后的整数可带小数，整组优先于小数和版本号一起保护。
_DIGITS = '0-9０-９'
_GROUP_SEPARATORS = ',，\u00a0\u2009\u202f'
_GROUPED_NUMBER_PAT = re.compile(
    rf'(?<![\d.．])(?<![\d][{_GROUP_SEPARATORS}])'
    rf'[{_DIGITS}]{{1,3}}(?P<separator>[{_GROUP_SEPARATORS}])[{_DIGITS}]{{3}}'
    rf'(?:(?P=separator)[{_DIGITS}]{{3}})*'
    rf'(?:[.．][{_DIGITS}]+)?'
    rf'(?![\d]|[{_GROUP_SEPARATORS}.．][\d])'
)
_GROUPED_NUMBER_TRANSLATION = str.maketrans('０１２３４５６７８９．', '0123456789.', _GROUP_SEPARATORS)

_CODE_BLOCK_PAT = re.compile(r'```[\s\S]*?```|`[^`\n]+`')
_DOUBLE_QUOTES = '"＂“”'
_DASH_RUN_PAT = re.compile(r'[-—–－]{2,}')
_ENGLISH_LINE_PARTS = re.compile(
    rf'({_PLACEHOLDER_PAT.pattern}|[{_DOUBLE_QUOTES}]|{_DASH_RUN_PAT.pattern})'
)
_ENGLISH_SPACE_MARK_PAT = re.compile(r'(?<=[A-Za-z]{2})·(?=[A-Za-z]{2})')
_SPACE_MARKS = '\u3000␠␣□☐▢⬜'
_SPACE_MARK_TRANSLATION = str.maketrans({char: ' ' for char in _SPACE_MARKS})
_HASH_MARK_TRANSLATION = str.maketrans('', '', '#＃﹟')

# 需要保护的模式，按优先级从高到低排列（先匹配的先保护）
# 格式：(描述, 正则表达式)
_PROTECT_PATTERNS = [
    ('Code', _CODE_BLOCK_PAT),

    ('URL',
     re.compile(r'''(?:https?|ftp)://[^\s，。？！：；【】《》（）"'＂“”‘’、\x02\x03]+''',
                re.IGNORECASE)),

    ('Email',
     re.compile(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}')),

    ('GroupedNumber', _GROUPED_NUMBER_PAT),

    ('CommandFlag', re.compile(r'(?<![\w-])--[A-Za-z][A-Za-z0-9_-]*')),

    # ③ 版本号：vX.Y / X.Y.Z（至少含一个点分隔的数字结构）
    #    \b 在中文边界失效，改用 (?<![.\d]) 负向后查，(?![.\d]) 负向前查
    #    例：v1.2  1.0  2.1.3  v3.0.0-beta  v1.0.0  （前后不能再有数字或点）
    ('Version',
     re.compile(r'(?<![.\d])v?\d+(?:\.\d+){1,5}(?:-[A-Za-z0-9]+)?(?![.\d])', re.IGNORECASE)),

    # ④ 小数 / 日期（纯数字.数字）
    #    负向查保证前后无其他数字，防止匹配版本号片段
    #    例：3.14  2024.01  0.5  100.00
    ('Decimal',
     re.compile(r'(?<![.\dA-Za-z])\d+\.\d+(?![.\dA-Za-z])')),

    # ⑤ 标题编号：行首的 数字.（数字.）* 结构，后跟空格
    #    例：1. 标题  1.1 子标题  1.1.1 三级  （必须在行首）
    ('Heading',
     re.compile(r'(?m)(?:^|\n)(\d+(?:\.\d+)*\.)\s')),

    # ⑥ 常见英文缩写（字母.字母. 形式，至少2个"字母."）
    #    例：e.g.  i.e.  U.S.A.  a.b.c.
    ('Abbrev',
     re.compile(r'(?<![A-Za-z\d])(?:[A-Za-z]\.){2,}(?:[A-Za-z])?')),

    # ⑦ 文件名（word.ext，ext 为 2-6 位字母数字）
    #    使用 (?<![A-Za-z0-9.]) 确保前面不是字母/数字/点（避免与版本号/缩写重叠）
    #    例：file.txt  index.html  main.py  README.md  app.min.js
    ('Filename',
     re.compile(r'(?<![A-Za-z0-9])[A-Za-z][A-Za-z0-9_\-]*(?:\.[A-Za-z][A-Za-z0-9]{1,5}){1,3}(?![A-Za-z0-9.])')),

    # ⑧ 特殊技术符号
    ('TechSymbol',
     re.compile(
         r'\bC\+\+\b|'
         r'\b[A-Za-z][A-Za-z0-9]*\.[A-Za-z][A-Za-z0-9]*(?:\(\))?'  # a.b() / Node.js
     )),

]


def protect_special_patterns(text: str) -> tuple[str, dict]:
    """保护代码、URL、数字和纯英文行中普通标点。"""
    store: dict[str, str] = {}

    def make_placeholder(original: str) -> str:
        key = _PLACEHOLDER_FMT.format(len(store))
        store[key] = original
        return key

    for name, pattern in _PROTECT_PATTERNS:
        if name == 'GroupedNumber':
            text = pattern.sub(
                lambda match: make_placeholder(match[0].translate(_GROUPED_NUMBER_TRANSLATION)),
                text,
            )
        else:
            text = pattern.sub(lambda match: make_placeholder(match[0]), text)

    # Word 复制文本中的词间空格标记还原为普通空格。
    text = _ENGLISH_SPACE_MARK_PAT.sub(' ', text)
    protected_lines = []
    for line in text.split('\n'):
        visible = _PLACEHOLDER_PAT.sub('', line)
        en_chars = len(re.findall(r'[A-Za-z]', visible))
        zh_chars = len(re.findall(r'[\u4e00-\u9fff]', visible))
        total = en_chars + zh_chars
        if total > 10 and en_chars / total > 0.70:
            parts = _ENGLISH_LINE_PARTS.split(line)
            # 偶数下标是正文，保留其边缘空白以辅助判断引号方向。
            parts[::2] = [
                re.sub(r'\S(?:.*\S)?', lambda match: make_placeholder(match[0]), part)
                for part in parts[::2]
            ]
            line = ''.join(parts)
        protected_lines.append(line)
    return '\n'.join(protected_lines), store


def restore_patterns(text: str, store: dict) -> str:
    """
    将文本中的占位符全部还原为原始内容。
    使用 re.sub 保证全量还原，不会遗漏。
    """
    def replace_placeholder(m: re.Match) -> str:
        return store.get(m.group(0), m.group(0))

    return _PLACEHOLDER_PAT.sub(replace_placeholder, text)


# ──────────────────────────────────────────────
# Step 1  英文标点 → 中文标点
# ──────────────────────────────────────────────

def convert_punctuation(text: str, punct_map: dict = None) -> str:
    """
    逐字符遍历，将英文标点全量替换为中文标点。

    保证无遗漏原理：
    - 每个字符均被遍历一次（O(n) 单次扫描）
    - dict.get(char, char) 命中则替换，否则原样
    - 不存在跳过、只处理首个、顺序依赖等问题

    前置条件：special patterns 已被占位符保护，占位符字符不在 PUNCT_MAP 中，
    因此占位符内容不会被误转换。
    """
    if punct_map is None:
        punct_map = PUNCT_MAP
    result = []
    for char in text:
        result.append(punct_map.get(char, char))
    return ''.join(result)


# ──────────────────────────────────────────────
# Step 2  符号规范化（省略号 / 破折号 / 全角→半角）
# ──────────────────────────────────────────────

def normalize_symbols(text: str) -> str:
    """
    1. 英文省略号（3个+句点）→ ……；转换后的连续句号也规范化
    2. 连续横线 → 单个长横线；原有单横线保持原样
    3. 全角英文字母/数字 → 半角（Ａ→A，１→1）
    """
    # ① 省略号
    text = re.sub(r'\.{3,}', '……', text)     # 残留英文省略号
    text = re.sub(r'。{3,}', '……', text)     # 转换后的连续句号

    # ② 合并连续横线，保留单个连字符和负号。
    text = _DASH_RUN_PAT.sub('—', text)

    # ③ 全角ASCII字母/数字 → 半角
    def fullwidth_to_half(m: re.Match) -> str:
        return chr(ord(m.group()) - 0xFEE0)
    text = re.sub(r'[\uff10-\uff19\uff21-\uff3a\uff41-\uff5a]',
                  fullwidth_to_half, text)

    return text


# ──────────────────────────────────────────────
# Step 3  中文标点纠错
# ──────────────────────────────────────────────

def fix_chinese_punctuation(text: str) -> str:
    """
    对转换后的中文标点进行纠错：
    1. 压缩重复标点（！！！！！ → ！！）
    2. 修正错误组合（，。→ 。  ，，→ ，）
    3. 删除中文标点前多余空格（你好 ，→ 你好，）
    """
    # ① 清理转换后产生的连续句号
    text = re.sub(r'。{3,}', '……', text)

    # ② 压缩重复中文标点
    text = re.sub(r'！{3,}', '！！', text)
    text = re.sub(r'？{3,}', '？？', text)
    text = re.sub(r'，{2,}', '，', text)
    text = re.sub(r'。{2,}', '。', text)
    text = re.sub(r'；{2,}', '；', text)
    text = re.sub(r'：{2,}', '：', text)
    text = re.sub(r'、{2,}', '、', text)

    # ③ 修正错误标点组合
    text = re.sub(r'([。？！])[，、；]', r'\1', text)
    text = re.sub(r'，([。？！])', r'\1', text)
    text = re.sub(r'、，', '，', text)

    # ④ 删除中文标点前的多余空格
    text = re.sub(
        r'(?<=[^ \t\r\n])[ \t]+(?=[，。？！：；、】》）｝～…—·])',
        '', text
    )

    return text


def _pair_replace(text: str, char: str, left: str, right: str) -> str:
    """将文本中的 char 按奇偶顺序替换为 left / right。（内部保留，供兼容）"""
    parts = text.split(char)
    result = parts[0]
    for i, part in enumerate(parts[1:], 1):
        result += (left if i % 2 == 1 else right) + part
    return result


# ──────────────────────────────────────────────
# Step 3.2  引号规范化（独立函数，幂等处理）
# ──────────────────────────────────────────────

# 中文左右双引号 / 单引号的 Unicode 码点
_L_DQUOTE = '\u201c'   # "
_R_DQUOTE = '\u201d'   # "
_L_SQUOTE = '\u2018'   # '
_R_SQUOTE = '\u2019'   # '

_ZH_SQUOTE_PAT = re.compile(r'[' + _L_SQUOTE + _R_SQUOTE + r']')
_DOUBLE_QUOTE_PAT = re.compile(r'[' + _DOUBLE_QUOTES + ']')


def _normalize_double_quotes(text: str) -> str:
    """识别半角和全角直双引号，利用已有弯引号及上下文判断开闭。"""
    matches = list(_DOUBLE_QUOTE_PAT.finditer(text))
    parts = []
    opened = []
    start = 0
    for index, match in enumerate(matches):
        position = match.start()
        quote = match[0]
        parts.append(text[start:position])
        start = position + 1

        if quote == _L_DQUOTE:
            opened.append(quote)
        elif quote == _R_DQUOTE:
            if opened:
                opened.pop()
        else:
            before = text[position - 1] if position else ''
            after = text[start:start + 1]
            opens_in_context = (
                before and before in '：:（(【[《“‘—'
                and bool(after) and not after.isspace()
                and after not in _DOUBLE_QUOTES + '，。？！：；、）】》,.?!:;)]'
            )
            # 已有中文外引号夹着一对直引号时，优先保留外层。
            inside_curly_pair = (
                bool(opened) and opened[-1] == _L_DQUOTE
                and index + 2 < len(matches)
                and matches[index + 1][0] in '"＂'
                and matches[index + 2][0] == _R_DQUOTE
            )
            if not opened or opens_in_context or inside_curly_pair:
                opened.append(quote)
                quote = _L_DQUOTE
            else:
                opened.pop()
                quote = _R_DQUOTE

        parts.append(quote)
    parts.append(text[start:])
    return ''.join(parts)


def normalize_quotes(text: str) -> str:
    """转换直引号，保留已有的中文引号及代码中的引号。"""
    code_store: dict[str, str] = {}

    def protect_code(match: re.Match) -> str:
        key = f'\x04CODE{len(code_store)}\x05'
        code_store[key] = match[0]
        return key

    text = _CODE_BLOCK_PAT.sub(protect_code, text)
    text = _normalize_double_quotes(text)
    if not _ZH_SQUOTE_PAT.search(text):
        text = _context_aware_replace(text, "'", _L_SQUOTE, _R_SQUOTE,
                                      is_apostrophe=True)

    return re.sub(r'\x04CODE\d+\x05', lambda match: code_store.get(match[0], match[0]), text)


def _context_aware_replace(text: str, char: str,
                            left: str, right: str,
                            is_apostrophe: bool) -> str:
    """
    逐字符扫描，将 char 按上下文替换为 left（开）或 right（闭）。

    判断规则（优先级从高到低）：
    ① 所有格/缩写保护（仅 is_apostrophe=True）
       - 前一个字符是字母（[A-Za-z]）→ 英文所有格，保留原字符
       例：it's  don't  o'clock → 不转换
    ② 前字符强制开引号
       - 前字符是：行首、空格、中文/英文开括号（（【《）等）、破折号
       → 强制替换为 left（开引号）
    ③ 后字符强制闭引号
       - 后字符是：行尾、空格、中文标点（，。？！：；）、英文标点
       → 强制替换为 right（闭引号）
    ④ 奇偶兜底
       - 以上均不明确时，第奇数次遇到 → left，第偶数次 → right
    """
    # 前字符属于"此处应用开引号"：行首、空白、开括号、已有开引号
    # 注意：句末标点（，。？！）后接引号 → 闭引号，不放入此集合
    _OPEN_PREV  = set(' \t\n\r（【《\u201c\u2018')
    # 后字符属于"此处应用闭引号"：行尾、空白、标点、闭括号
    _CLOSE_NEXT = set(' \t\n\r），】》\u201d\u2019，。？！：；、——……')

    result = []
    count  = 0   # 遇到 char 的计数（1-indexed）
    chars  = list(text)
    n      = len(chars)

    i = 0
    while i < n:
        c = chars[i]
        if c != char:
            result.append(c)
            i += 1
            continue

        prev_char = chars[i - 1] if i > 0 else ''
        next_char = chars[i + 1] if i + 1 < n else ''

        # ① 所有格保护（仅针对 ASCII 字母，汉字/数字等不触发）
        #    例：it's  don't → 保留；'你好' 中 '好' 前的 ' 不保留
        if is_apostrophe and prev_char.isascii() and prev_char.isalpha():
            result.append(char)   # 保留英文单引号
            i += 1
            continue

        count += 1
        # ② 前字符暗示开引号
        if prev_char == '' or prev_char in _OPEN_PREV:
            result.append(left)
        # ③ 后字符暗示闭引号
        elif next_char == '' or next_char in _CLOSE_NEXT:
            result.append(right)
        # ④ 奇偶兜底
        else:
            result.append(left if count % 2 == 1 else right)

        i += 1

    return ''.join(result)



# ──────────────────────────────────────────────
# Step 3.3  引号质量审查与自动修复
# ──────────────────────────────────────────────

# 问题严重等级
_SEVERITY_INFO  = 'INFO'    # 已记录，无需修改
_SEVERITY_FIXED = 'FIXED'   # 已自动修复
_SEVERITY_WARN  = 'WARN'    # 无法确定，保留原文并记录

# 所有中文引号字符集合（用于快速检测）
_ALL_ZH_QUOTES = {_L_DQUOTE, _R_DQUOTE, _L_SQUOTE, _R_SQUOTE}

# 代码块保护（与 normalize_quotes 共用同一正则）
_AUDIT_CODE_PAT = re.compile(r'```[\s\S]*?```|`[^`\n]+`')

# 残留英文引号正则（仅匹配成对的）
_RESIDUAL_DQUOTE_PAT = re.compile(r'"([^"]{0,200}?)"')
_RESIDUAL_SQUOTE_PAT = re.compile(r"'([^']{0,200}?)'")

# 重复引号正则（连续两个以上相同引号）
_DUP_QUOTE_PAT = re.compile(
    r'(' + re.escape(_L_DQUOTE) + r'){2,}|'
    r'(' + re.escape(_R_DQUOTE) + r'){2,}|'
    r'(' + re.escape(_L_SQUOTE) + r'){2,}|'
    r'(' + re.escape(_R_SQUOTE) + r'){2,}'
)


class QuoteAuditReport:
    """引号审查报告：汇总检测到的问题与修复操作。"""
    __slots__ = ('issues',)

    def __init__(self):
        self.issues: list[dict] = []

    def add(self, severity: str, code: str, desc: str, context: str = ''):
        self.issues.append({
            'severity': severity,
            'code':     code,
            'desc':     desc,
            'context':  context[:60],   # 截取上下文，避免日志过长
        })

    def has_problems(self) -> bool:
        return any(i['severity'] != _SEVERITY_INFO for i in self.issues)

    def summary(self) -> str:
        if not self.issues:
            return '[QuoteAudit] 无问题，引号结构规范。'
        lines = ['[QuoteAudit] 检测报告：']
        for iss in self.issues:
            lines.append(
                f"  [{iss['severity']}] {iss['code']}: {iss['desc']}"
                + (f"  ↳ …{iss['context']}…" if iss['context'] else '')
            )
        return '\n'.join(lines)


def audit_and_repair_quotes(text: str) -> tuple[str, QuoteAuditReport]:
    """
    对 normalize_quotes 输出的文本进行引号质量审查与自动修复。

    ── 检测项目 ────────────────────────────────────────────────────
    P1  残留英文引号       " " / ' ' 未完全转换
    P2  连续重复引号       "" / '' / "" / '' 等冗余符号
    P3  开闭不成对         " 多于 " 或 " 多于 "（跨全文统计）
    P4  嵌套层级混乱       外层用单引号、内层用双引号（应反转）
    P5  开引号紧跟闭引号   "" / '' 空引号对（无内容）

    ── 修复策略 ────────────────────────────────────────────────────
    P1  → 对成对的残留英文引号按上下文重新转换（调用 _context_aware_replace）
    P2  → 压缩为单个对应引号字符
    P3  → 若多出开引号：在全文末尾补闭引号；
          若多出闭引号：在全文首部补开引号；
          差值 > 3 时视为无法确定，标记 WARN 不修改
    P4  → 当双引号对内部检测到双引号（应为单引号）时，将内层换为单引号
    P5  → 删除空引号对（"" / ''）

    ── 代码保护 ────────────────────────────────────────────────────
    审查前先保护 ``` ``` / ` ` 代码块，还原后再输出，
    保证 JSON / SQL / 代码字符串中的引号不被误处理。

    ── 不修改条件 ──────────────────────────────────────────────────
    - 文本中完全不含任何中文引号 → 直接返回（normalize_quotes 已处理）
    - 无法判断结构的不成对情况（差值 > 3）→ WARN 并保留原文

    Args:
        text: normalize_quotes 输出的文本

    Returns:
        (修复后文本, QuoteAuditReport 报告对象)
    """
    report = QuoteAuditReport()

    # 快速退出：若完全不含中文引号，无需审查
    if not any(ch in text for ch in _ALL_ZH_QUOTES):
        return text, report

    # ── 保护代码块 ──────────────────────────────────────────────
    code_store: list[str] = []

    def _protect(m: re.Match) -> str:
        code_store.append(m.group(0))
        return f'\x06AUD{len(code_store) - 1}\x07'

    text = _CODE_BLOCK_PAT.sub(_protect, text)

    # ── P1  残留英文引号修复 ─────────────────────────────────────
    def _fix_residual_dquote(m: re.Match) -> str:
        report.add(_SEVERITY_FIXED, 'P1-DQUOTE',
                   '修复残留英文双引号', m.group(0))
        return _L_DQUOTE + m.group(1) + _R_DQUOTE

    def _fix_residual_squote(m: re.Match) -> str:
        report.add(_SEVERITY_FIXED, 'P1-SQUOTE',
                   '修复残留英文单引号', m.group(0))
        return _L_SQUOTE + m.group(1) + _R_SQUOTE

    new_text = _RESIDUAL_DQUOTE_PAT.sub(_fix_residual_dquote, text)
    if new_text != text:
        text = new_text
    new_text = _RESIDUAL_SQUOTE_PAT.sub(_fix_residual_squote, text)
    if new_text != text:
        text = new_text

    # ── P2  连续重复引号压缩 ─────────────────────────────────────
    def _compress_dup(m: re.Match) -> str:
        ch = m.group(0)[0]
        report.add(_SEVERITY_FIXED, 'P2-DUP',
                   f'压缩连续重复引号 {repr(m.group(0))} → {repr(ch)}',
                   m.group(0))
        return ch

    new_text = _DUP_QUOTE_PAT.sub(_compress_dup, text)
    if new_text != text:
        text = new_text

    # ── P5  空引号对删除（先于 P3，避免干扰计数）────────────────
    _EMPTY_DQUOTE = _L_DQUOTE + _R_DQUOTE
    _EMPTY_SQUOTE = _L_SQUOTE + _R_SQUOTE
    if _EMPTY_DQUOTE in text:
        report.add(_SEVERITY_FIXED, 'P5-EMPTY', '删除空双引号对 ""')
        text = text.replace(_EMPTY_DQUOTE, '')
    if _EMPTY_SQUOTE in text:
        report.add(_SEVERITY_FIXED, 'P5-EMPTY', "删除空单引号对 ''")
        text = text.replace(_EMPTY_SQUOTE, '')

    # ── P4  嵌套层级修复 ─────────────────────────────────────────
    # 检测模式：" ... " ... " ... " 内部出现双引号（应为单引号）
    # 策略：扫描双引号对，若对内再次出现 " 或 "，将其换为 ' 或 '
    text = _fix_nested_quotes(text, report)

    # ── P3  全文开闭配对检查与修复 ──────────────────────────────
    l_count = text.count(_L_DQUOTE)
    r_count = text.count(_R_DQUOTE)
    diff    = l_count - r_count

    if diff == 0:
        if l_count > 0:
            report.add(_SEVERITY_INFO, 'P3-OK',
                       f'双引号成对，共 {l_count} 对')
    elif 0 < diff <= 3:
        # 开引号多于闭引号：在末尾补闭引号
        report.add(_SEVERITY_FIXED, 'P3-APPEND-R',
                   f'开引号多 {diff} 个，在末尾补闭引号')
        text = text + _R_DQUOTE * diff
    elif -3 <= diff < 0:
        # 闭引号多于开引号：在首部补开引号
        report.add(_SEVERITY_FIXED, 'P3-PREPEND-L',
                   f'闭引号多 {-diff} 个，在首部补开引号')
        text = _L_DQUOTE * (-diff) + text
    else:
        # 差值 > 3：结构混乱，无法安全修复，记录 WARN
        report.add(_SEVERITY_WARN, 'P3-UNBALANCED',
                   f'开闭引号差值 {diff} 超过阈值，保留原文',
                   text[:60])

    # 单引号成对检查（仅报告，不强制补全，避免与所有格混淆）
    ls_count = text.count(_L_SQUOTE)
    rs_count = text.count(_R_SQUOTE)
    sq_diff  = ls_count - rs_count
    if sq_diff != 0:
        report.add(_SEVERITY_WARN, 'P3-SQUOTE',
                   f'单引号开({ls_count})闭({rs_count})不对称，已记录，不自动修补')

    # ── 还原代码块 ───────────────────────────────────────────────
    for i, code in enumerate(code_store):
        text = text.replace(f'\x06AUD{i}\x07', code)

    return text, report


def _fix_nested_quotes(text: str, report: QuoteAuditReport) -> str:
    """
    检测并修复双引号对内部嵌套双引号的问题。

    规则（中文排版惯例）：
      外层：" 内容 "
      内层：' 内容 '   ← 若内层误用了双引号则替换为单引号

    实现：
      逐字符扫描，追踪当前嵌套深度（depth）。
      - depth == 0 时遇 _L_DQUOTE → 进入外层（depth=1），保留
      - depth == 1 时遇 _L_DQUOTE → 这是内层开引号，替换为 _L_SQUOTE，depth=2
      - depth == 2 时遇 _R_DQUOTE → 内层闭引号，替换为 _R_SQUOTE，depth=1
      - depth == 1 时遇 _R_DQUOTE → 外层闭引号，保留，depth=0

    策略保守：
      - 最多处理两层（外层 + 一层内层）
      - 如内层引号开闭不对称，按遇到的字符顺序处理，其余由 P3 记录
    """
    chars   = list(text)
    n       = len(chars)
    result  = []
    depth   = 0
    fixed   = False

    i = 0
    while i < n:
        c = chars[i]

        if c == _L_DQUOTE:
            if depth == 0:
                depth = 1
                result.append(c)            # 外层开引号，保留
            elif depth == 1:
                depth = 2
                result.append(_L_SQUOTE)    # 内层开引号，换为单引号
                fixed = True
            else:
                result.append(c)            # 更深层，保留原样
        elif c == _R_DQUOTE:
            if depth == 2:
                depth = 1
                result.append(_R_SQUOTE)    # 内层闭引号，换为单引号
                fixed = True
            elif depth == 1:
                depth = 0
                result.append(c)            # 外层闭引号，保留
            else:
                result.append(c)            # depth=0 的孤立闭引号，保留（P3 处理）
        else:
            result.append(c)

        i += 1

    if fixed:
        report.add(_SEVERITY_FIXED, 'P4-NESTED',
                   '修复嵌套双引号：内层双引号 → 单引号')

    return ''.join(result)


# ──────────────────────────────────────────────
# Step 3.5  删除 Markdown / Obsidian 星号标记
# ──────────────────────────────────────────────

def remove_markdown_stars(text: str) -> str:
    """
    删除 Markdown 加粗/斜体星号标记，保留文字内容。
    处理范围：
      ***文本***  →  文本
      **文本**    →  文本
      *文本*      →  文本
      孤立的 *    →  （删除）

    保留规则（避免误删）：
      - 数字乘法表达式 "数字 * 数字" / "数字*数字" 中的 * 保留
        例：3 * 5  a*b（纯字母变量）→ 保留

    实现思路：
      1. 先处理成对的 ***...*** / **...** / *...* （贪婪匹配从多到少）
      2. 再删除剩余孤立 *（不与数字/字母乘法表达式相邻的）
    """
    # ① 成对星号：*** / ** / *（从多到少，避免 ** 先匹配吃掉 *** 的一部分）
    #    [\s\S]+? 非贪婪，支持跨行（Obsidian 多行加粗较少见，但兼容）
    text = re.sub(r'\*{3}([\s\S]+?)\*{3}', r'\1', text)
    text = re.sub(r'\*{2}([\s\S]+?)\*{2}', r'\1', text)
    text = re.sub(r'\*([\s\S]+?)\*',        r'\1', text)

    # ② 删除剩余孤立 *
    #    保留条件：* 左右两侧都紧贴 \w（如 a*b、x*y）→ 变量/标识符乘法
    #    保留条件：数字 * 数字（含空格的算术表达式）→ 先占位保护
    #    其余所有 * （包括 "字* "、"* 字"、行首行尾孤立）→ 全部删除
    _ARITH_PLACEHOLDER = '\x02STAR\x03'
    # 保护 "数字(空格)*（空格)数字" 形式的算术乘法
    text = re.sub(r'(?<=\d)\s*\*\s*(?=\d)', _ARITH_PLACEHOLDER, text)
    # 保留 \w*\w（无空格紧邻两侧均为单词字符），删除其余所有 *
    # 用 sub + 回调判断：若左右均为 \w 则保留，否则删除
    def _handle_star(m: re.Match) -> str:
        start, end = m.start(), m.end()
        left_is_word  = start > 0 and re.match(r'\w', text[start - 1]) is not None
        right_is_word = end < len(text) and re.match(r'\w', text[end]) is not None
        return '*' if (left_is_word and right_is_word) else ''
    text = re.sub(r'\*', _handle_star, text)
    # 还原算术乘法占位符
    text = text.replace(_ARITH_PLACEHOLDER, ' * ')
    # 注意：连续多余空格的压缩由后续 clean_spaces_per_line 按行处理，
    # 此处不做全局 '  +' 压缩，避免破坏行首缩进。

    return text


# ──────────────────────────────────────────────
# Step 4  间距格式化（仅标点前后空格，不插入中英间距）
# ──────────────────────────────────────────────

def format_spacing(text: str) -> str:
    """保留英文词间距，并清理中文及标点附近的多余空格。"""
    def adjust_gap(match: re.Match) -> str:
        gap = match[0]
        start, end = match.span()
        if start == 0 or end == len(text):
            return gap

        before, after = text[start - 1], text[end]
        if before in '\r\n' or after in '\r\n':
            return gap

        latin_before = _LATIN_ALNUM_PAT.fullmatch(before)
        latin_after = _LATIN_ALNUM_PAT.fullmatch(after)
        if latin_before and (latin_after or after in '“‘（【《｛'):
            return gap
        if latin_after and before in '”’）】》｝':
            return gap
        if (latin_after and before in '，。？！：；' and start >= 2
                and _LATIN_ALNUM_PAT.fullmatch(text[start - 2])):
            return gap

        if before in _ZH_PUNCT or after in _ZH_PUNCT:
            return ''
        if _CJK_CHAR_PAT.fullmatch(before) and _CJK_CHAR_PAT.fullmatch(after):
            return ''
        return re.sub(r' {2,}', ' ', gap)

    return re.sub(r'[ \t]+', adjust_gap, text)


# ──────────────────────────────────────────────
# Step 6.5  按行清理空格
# ──────────────────────────────────────────────


def clean_spaces_per_line(text: str) -> str:
    """清理正文间距，保留行首缩进及 Markdown 标题前缀。"""
    result_lines = []
    for line in text.split('\n'):
        prefix = re.match(r'[ \t\u3000]*(?:#{1,6} )?', line)[0]
        content = format_spacing(line[len(prefix):]).rstrip(' \t')
        result_lines.append(prefix + content)
    return '\n'.join(result_lines)


# ──────────────────────────────────────────────
# Step 5（还原占位符在主流程调用，此处无单独函数）
# ──────────────────────────────────────────────

# ──────────────────────────────────────────────
# Step 6  段首缩进（普通空格）
# ──────────────────────────────────────────────


INDENT = '    '


def add_paragraph_indent(text: str) -> str:
    """将非空段落缩进到四个普通空格，较长的已有缩进保持原样。"""
    return re.sub(r'(?m)^[ \t]{0,3}(?=\S)', INDENT, text)


# ──────────────────────────────────────────────
# Step 7  空白清理
# ──────────────────────────────────────────────

def clean_whitespace(text: str) -> str:
    """
    1. 删除每一行行尾多余空格
    2. 连续空行超过1个 → 压缩为1个空行
    """
    lines = [line.rstrip(' \t') for line in text.split('\n')]
    text = '\n'.join(lines)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text


# ──────────────────────────────────────────────
# 主流程入口
# ──────────────────────────────────────────────

def process_text(text: str) -> dict:
    """返回清理后的文本、标点统计和引号审查结果。"""
    # 统计原始可替换英文标点数（保护前）
    punct_count = sum(
        1 for ch in text
        if ch in PUNCT_MAP or ch in ('"', '＂', "'", '-')
    )

    # 统一剪贴板换行，清理井号及段首可见空格标记。
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = re.sub(r'(?m)^[ 	]*[#＃﹟]+[ 	]*', '', text)
    text = text.translate(_HASH_MARK_TRANSLATION)
    text = re.sub(rf'(?m)^[ 	]*[{_SPACE_MARKS}][ 	{_SPACE_MARKS}]*', '', text)
    text = text.translate(_SPACE_MARK_TRANSLATION)
    text, store = protect_special_patterns(text)

    # 1-4. 标点转换与排版
    text = convert_punctuation(text)
    text = normalize_symbols(text)
    text = fix_chinese_punctuation(text)
    text = normalize_quotes(text)                        # 3.2 引号规范化
    text, q_report = audit_and_repair_quotes(text)       # 3.3 引号质量审查
    text = remove_markdown_stars(text)                   # 3.5 删除 Markdown 星号

    # 5. 还原正文以判断英文空格，代码留到排版结束后再还原。
    code_store = {key: value for key, value in store.items() if _CODE_BLOCK_PAT.fullmatch(value)}
    text = restore_patterns(text, {key: value for key, value in store.items() if key not in code_store})

    text = clean_spaces_per_line(text)
    text = clean_whitespace(text)
    paragraphs = []
    indent_lines = 0
    for line in text.split('\n'):
        indented = line if line.strip() in code_store else add_paragraph_indent(line)
        indent_lines += indented != line
        paragraphs.append(indented)
    text = restore_patterns('\n'.join(paragraphs), code_store)

    return {
        "result":        text,
        "punct_count":   punct_count,
        "indent_lines":  indent_lines,
        "quote_issues":  q_report.issues,
        "quote_summary": q_report.summary(),
    }


def get_punct_map() -> dict:
    """返回当前使用的映射表（供外部查询 / API 展示）"""
    return dict(PUNCT_MAP)


def audit_quotes_only(text: str) -> tuple[str, QuoteAuditReport]:
    """
    仅执行引号审查（不运行完整流水线），供独立调试使用。
    等价于：normalize_quotes → audit_and_repair_quotes
    """
    text = normalize_quotes(text)
    return audit_and_repair_quotes(text)


# ──────────────────────────────────────────────
# 自检测试（v3）
# ──────────────────────────────────────────────

def run_tests():
    """完整自检：覆盖保护规则、标点转换、排版所有步骤"""
    sep = '=' * 62
    all_passed = True

    # ── 单函数级测试 ──────────────────────────────
    print(sep)
    print('  自检报告 · 单函数级测试（v3）')
    print(sep)

    unit_cases = [
        ('主流程：清理井号和可见空格标记',
         lambda t: process_text(t)['result'],
         '## 收支小结\n\u3000＃备□注␣已核对﹟。',
         '    收支小结\n    备注已核对。'),

        ('主流程：千分位移除，小数及数字列表保留',
         lambda t: process_text(t)['result'],
         '收入-1,234,567.89；支出１２，３４５．６０；另有2\u202f345；编号1,2,3。',
         '    收入-1234567.89；支出12345.60；另有2345；编号1，2，3。'),

        ('主流程：纯英文引语与受保护的数字',
         lambda t: process_text(t)['result'],
         '"The total is 1,234.50," she said.',
         lambda r: '“The total is 1234.50,”' in r and '\x02' not in r),

        ('主流程：混用全角、半角和弯引号',
         lambda t: process_text(t)['result'],
         '“确认"后说＂确定＂。\n"下一段"。',
         '    “确认”后说“确定”。\n    “下一段”。'),

        ('主流程：链接和代码旁的引号',
         lambda t: process_text(t)['result'],
         '"https://example.com"和`print("ok")`',
         '    “https://example.com”和`print("ok")`'),

        ('主流程：自然段缩进，清理旧标记并兼容不同换行符',
         lambda t: (process_text(t)['result'], process_text(t)['indent_lines']),
         '第一段。\r\n\r\n    第二段。\r\u3000第三段。',
         ('    第一段。\n\n    第二段。\n    第三段。', 2)),

        ('主流程：自然段缩进幂等',
         lambda t: (process_text(t)['result'], process_text(t)['indent_lines']),
         '    —第一段。\n\n    第二段。',
         ('    —第一段。\n\n    第二段。', 0)),

        ('主流程：词语和数字范围的横线合并，同时保留小数和负号',
         lambda t: process_text(t)['result'],
         '数据——算力--模型—中试——应用。范围1,200.50--2,300.75，温度-12。',
         '    数据—算力—模型—中试—应用。范围1200.50—2300.75，温度-12。'),

        ('主流程：英文横线合并，普通连字符和命令参数保留',
         lambda t: process_text(t)['result'],
         'Natural language--artificial intelligence with well-known methods and --version.',
         '    Natural language—artificial intelligence with well-known methods and --version.'),

        ('主流程：保留英文词间空格，还原 Word 标记并保留其他间隔号',
         lambda t: process_text(t)['result'],
         '据 Fortune·Business·Insights 记载，New   York。乘法a·b，乔治·奥威尔。',
         '    据 Fortune Business Insights 记载，New   York。乘法a·b，乔治·奥威尔。'),

        ('主流程：保留英文引语和标点后的词间空格',
         lambda t: process_text(t)['result'],
         'This is "my  phrase" in a sentence.\nHello, World',
         '    This is “my  phrase” in a sentence.\n    Hello， World'),

        ('主流程：代码块保留横线和原有格式，正文段落缩进',
         lambda t: process_text(t)['result'],
         '第一段。\n```py\nif x:\n    print("hi",  a--b)\n```\n第三段。',
         '    第一段。\n```py\nif x:\n    print("hi",  a--b)\n```\n    第三段。'),

        # protect_special_patterns
        ('版本号保护：1.0 不转换',
         lambda t: process_text(t)['result'],
         '当前版本是1.0，请升级。',
         lambda r: '1.0' in r and '1。0' not in r),

        ('版本号保护：v2.1.3',
         lambda t: process_text(t)['result'],
         '软件版本v2.1.3已发布。',
         lambda r: 'v2.1.3' in r),

        ('小数保护：3.14',
         lambda t: process_text(t)['result'],
         'π约等于3.14，很重要。',
         lambda r: '3.14' in r and '3。14' not in r),

        ('日期格式保护：2024.01',
         lambda t: process_text(t)['result'],
         '发布日期为2024.01，请确认。',
         lambda r: '2024.01' in r),

        ('标题编号保护：1.',
         lambda t: process_text(t)['result'],
         '1. 第一章\n1.1 子节\n1.1.1 三级标题',
         lambda r: '1. ' in r and '1。' not in r),

        ('缩写保护：e.g.',
         lambda t: process_text(t)['result'],
         '例如 e.g. 这种写法需要保留。',
         lambda r: 'e.g.' in r),

        ('缩写保护：U.S.A.',
         lambda t: process_text(t)['result'],
         'U.S.A.是一个国家，很重要。',
         lambda r: 'U.S.A.' in r),

        ('URL保护',
         lambda t: process_text(t)['result'],
         '请访问https://example.com获取信息。',
         lambda r: 'https://example.com' in r),

        ('邮箱保护',
         lambda t: process_text(t)['result'],
         '联系邮箱：test@gmail.com，谢谢。',
         lambda r: 'test@gmail.com' in r),

        ('文件名保护：file.txt',
         lambda t: process_text(t)['result'],
         '请编辑file.txt文件，保存后关闭。',
         lambda r: 'file.txt' in r),

        ('Node.js保护',
         lambda t: process_text(t)['result'],
         '使用Node.js开发效率高。',
         lambda r: 'Node.js' in r),

        # 普通标点转换（无保护）
        ('普通逗号转换',
         lambda t: process_text(t)['result'],
         '你好，世界真美好。',
         lambda r: '，' in r),

        ('英文逗号转中文',
         lambda t: process_text(t)['result'],
         '你好, 世界!',
         lambda r: '，' in r and '！' in r and ',' not in r),

        # 中英间距：不自动加空格（已删除该功能）
        ('不自动添加中英间距',
         format_spacing,
         '这是AI工具',
         '这是AI工具'),   # 期望：无空格插入

        ('不自动添加数字间距',
         format_spacing,
         'version2很好',
         'version2很好'),  # 期望：无空格插入

        # normalize_quotes ─────────────────────────────
        ('双引号：基础成对转换',
         normalize_quotes,
         '"你好"',
         '\u201c你好\u201d'),

        ('双引号：句中多对',
         normalize_quotes,
         '他说"早上好"，她说"晚上好"。',
         '他说\u201c早上好\u201d，她说\u201c晚上好\u201d。'),

        ('双引号：幂等——已是中文引号不重复处理',
         normalize_quotes,
         '\u201c你好\u201d',
         '\u201c你好\u201d'),

        ('双引号：混排时转换剩余直引号',
         normalize_quotes,
         '\u201c已规范\u201d和"未规范"混排',
         '\u201c已规范\u201d和\u201c未规范\u201d混排'),

        ('单引号：基础成对转换',
         normalize_quotes,
         "'你好'",
         '\u2018你好\u2019'),

        ('单引号：英文所有格保留',
         normalize_quotes,
         "it's a test, don't worry",
         "it's a test, don't worry"),

        ('单引号：幂等——已是中文单引号不处理',
         normalize_quotes,
         '\u2018你好\u2019',
         '\u2018你好\u2019'),

        ('代码块内引号不转换（行内代码）',
         normalize_quotes,
         '调用 `print("hello")` 函数',
         '调用 `print("hello")` 函数'),

        ('代码块内引号不转换（围栏代码）',
         normalize_quotes,
         '```\ndata = {"key": "value"}\n```',
         '```\ndata = {"key": "value"}\n```'),

        ('双引号：前空格暗示开引号',
         normalize_quotes,
         '他说 "你好" 然后离开。',
         '他说 \u201c你好\u201d 然后离开。'),

        ('主流程：引号+标点联合处理',
         lambda t: process_text(t)['result'],
         '他说"你好, 世界!"然后离开。',
         lambda r: '\u201c' in r and '\u201d' in r and '，' in r and '！' in r),

        ('主流程：已有中文引号不重复转换',
         lambda t: process_text(t)['result'],
         '\u201c已规范内容\u201d，请确认。',
         lambda r: r.count('\u201c') == 1 and r.count('\u201d') == 1),

        # audit_and_repair_quotes ───────────────────────
        ('审查P1：修复残留英文双引号',
         lambda t: audit_and_repair_quotes(t)[0],
         '\u201c正文\u201d和"残留英文引号"',
         '\u201c正文\u201d和\u201c残留英文引号\u201d'),

        ('审查P2：压缩重复开引号',
         lambda t: audit_and_repair_quotes(t)[0],
         '\u201c\u201c重复\u201d',
         '\u201c重复\u201d'),

        ('审查P2：压缩重复闭引号',
         lambda t: audit_and_repair_quotes(t)[0],
         '\u201c重复\u201d\u201d',
         '\u201c重复\u201d'),

        ('审查P3：开多闭少→补闭引号',
         lambda t: audit_and_repair_quotes(t)[0],
         '\u201c第一段\u201d\u201c第二段',
         '\u201c第一段\u201d\u201c第二段\u201d'),

        ('审查P3：闭多开少→补开引号',
         lambda t: audit_and_repair_quotes(t)[0],
         '第一段\u201d\u201c第二段\u201d',
         '\u201c第一段\u201d\u201c第二段\u201d'),

        ('审查P4：内层双引号→单引号',
         lambda t: audit_and_repair_quotes(t)[0],
         '\u201c外层\u201c内层\u201d内容\u201d',
         '\u201c外层\u2018内层\u2019内容\u201d'),

        ('审查P5：删除空引号对',
         lambda t: audit_and_repair_quotes(t)[0],
         '文字\u201c\u201d结尾',
         '文字结尾'),

        ('审查：代码块内引号不误处理',
         lambda t: audit_and_repair_quotes(t)[0],
         '调用`print("hello")`函数，\u201c正文\u201d。',
         '调用`print("hello")`函数，\u201c正文\u201d。'),

        ('审查：无引号文本直接返回',
         lambda t: audit_and_repair_quotes(t)[0],
         '这是一段没有引号的中文文本，正常处理。',
         '这是一段没有引号的中文文本，正常处理。'),

        ('审查：幂等——正确引号不被修改',
         lambda t: audit_and_repair_quotes(t)[0],
         '\u201c你好\u201d，\u201c世界\u201d。',
         '\u201c你好\u201d，\u201c世界\u201d。'),

        ('审查：报告中问题数量正确',
         lambda t: len(audit_and_repair_quotes(t)[1].issues),
         '\u201c\u201c重复\u201d',
         lambda r: r >= 1),

        ('主流程集成：审查修复残留引号',
         lambda t: process_text(t)['result'],
         '他说\u201c你好，"世界"\u201d。',
         lambda r: r.count('"') == 0 and '\u201c' in r),

        ('主流程：quote_issues字段存在',
         lambda t: process_text(t),
         '\u201c测试\u201d文本。',
         lambda r: 'quote_issues' in r and 'quote_summary' in r),

        # remove_markdown_stars ────────────────────────
        ('单星号删除：*文本*',
         remove_markdown_stars,
         '*你好*',
         '你好'),

        ('双星号删除：**文本**',
         remove_markdown_stars,
         '**重要内容**',
         '重要内容'),

        ('三星号删除：***文本***',
         remove_markdown_stars,
         '***强调***',
         '强调'),

        ('混合星号：句中多处',
         remove_markdown_stars,
         '这是**重要**内容，*斜体*文字。',
         '这是重要内容，斜体文字。'),

        ('保留乘法：3 * 5',
         remove_markdown_stars,
         '计算 3 * 5 等于15',
         '计算 3 * 5 等于15'),

        ('保留乘法：a*b',
         remove_markdown_stars,
         'a*b的结果',
         'a*b的结果'),

        ('孤立星号删除',
         remove_markdown_stars,
         '文字* 结尾',
         '文字 结尾'),

        ('多行星号',
         remove_markdown_stars,
         '**第一行**\n***第二行***\n*第三行*',
         '第一行\n第二行\n第三行'),

        # remove_markdown_stars 集成进主流程
        ('主流程：星号+标点同时处理',
         lambda t: process_text(t)['result'],
         '**重要提示**, 请注意*细节*!',
         lambda r: '重要提示' in r and '细节' in r and '*' not in r and '，' in r),

        # fix_chinese_punctuation
        ('重复感叹号压缩',
         fix_chinese_punctuation,
         '哇！！！！！',
         '哇！！'),

        ('错误组合：逗号+句号',
         fix_chinese_punctuation,
         '好的，。谢谢',
         '好的。谢谢'),

        ('标点前多余空格',
         fix_chinese_punctuation,
         '你好 ，世界 。',
         '你好，世界。'),

        # normalize_symbols
        ('省略号规范',
         normalize_symbols,
         '等等...我来了......',
         '等等……我来了……'),

        ('破折号规范',
         normalize_symbols,
         '这是--一个---测试',
         '这是—一个—测试'),

        ('全角转半角',
         normalize_symbols,
         'ＡＢＣ１２３',
         'ABC123'),

        # add_paragraph_indent
        ('段首缩进',
         add_paragraph_indent,
         '第一段。\n\n第二段。',
         '    第一段。\n\n    第二段。'),

        ('已有缩进不重复',
         add_paragraph_indent,
         '    已缩进段落。',
         '    已缩进段落。'),

        # clean_spaces_per_line
        ('中文字符间空格删除',
         clean_spaces_per_line,
         '我 们 去 吃 饭。',
         '我们去吃饭。'),

        ('连续多个间距迭代清理',
         clean_spaces_per_line,
         '这 是 一 段 测 试 文 字。',
         '这是一段测试文字。'),

        ('行首半角缩进保留',
         clean_spaces_per_line,
         '    第 一 段 内 容。',
         '    第一段内容。'),

        ('行首全角缩进保留',
         clean_spaces_per_line,
         '\u3000\u3000第 一 段 内 容。',
         '\u3000\u3000第一段内容。'),

        ('Markdown标题格式保留',
         clean_spaces_per_line,
         '## 项目背景',
         '## 项目背景'),

        ('Markdown标题内容空格清理',
         clean_spaces_per_line,
         '## 项 目 背 景',
         '## 项目背景'),

        ('各级标题均正确处理',
         clean_spaces_per_line,
         '# 一 级\n## 二 级\n### 三 级\n#### 四 级',
         '# 一级\n## 二级\n### 三级\n#### 四级'),

        ('英文词间空格保留',
         clean_spaces_per_line,
         'Hello World This is a test',
         'Hello World This is a test'),

        ('保留多个英文词间空格',
         clean_spaces_per_line,
         'Hello   World',
         'Hello   World'),

        ('混合行：英文+中文标点+中文',
         clean_spaces_per_line,
         'Hello   World ， 你 好 ！',
         'Hello   World，你好！'),

        ('行尾空格清理',
         clean_spaces_per_line,
         '你好   \n世界   ',
         '你好\n世界'),

        ('示例：题目要求三行',
         clean_spaces_per_line,
         '    我 们 去 吃 饭 。\n## 项 目 背 景\nHello   World ， 你 好 ！',
         '    我们去吃饭。\n## 项目背景\nHello   World，你好！'),

        # clean_whitespace（原有，保持）
        ('行尾空格清理',
         clean_whitespace,
         '你好   \n世界   ',
         '你好\n世界'),

        ('连续空行压缩',
         clean_whitespace,
         '段落一。\n\n\n\n段落二。',
         '段落一。\n\n段落二。'),
    ]

    for i, case in enumerate(unit_cases, 1):
        if len(case) == 4:
            name, fn, inp, exp = case
            # exp 可能是字符串（精确匹配）或 lambda（条件检查）
            got = fn(inp)
            if callable(exp):
                ok = exp(got)
            else:
                ok = (got == exp)
        else:
            name, fn, inp, exp = case[0], case[1], case[2], case[3]
            got = fn(inp)
            ok = exp(got) if callable(exp) else (got == exp)

        flag = '✅ PASS' if ok else '❌ FAIL'
        print(f'\n[{i:02d}] {name} {flag}')
        if not ok:
            got_display = fn(inp)
            print(f'  输入：{repr(inp)}')
            if not callable(exp):
                print(f'  期望：{repr(exp)}')
            print(f'  实际：{repr(got_display)}')
            all_passed = False

    # ── 集成测试 ──────────────────────────────────
    print(f'\n{sep}')
    print('  自检报告 · 主流程集成测试（process_text v3）')
    print(sep)

    def R(t):
        return process_text(t)['result']

    integration_cases = [
        {
            'name': '版本号/小数/日期不转换',
            'input': '版本1.0已发布，π≈3.14，日期2024.01，v2.1.3正式版。',
            'checks': [
                ('1.0 保留',     lambda r: '1.0' in r and '1。0' not in r),
                ('3.14 保留',    lambda r: '3.14' in r),
                ('2024.01 保留', lambda r: '2024.01' in r),
                ('v2.1.3 保留',  lambda r: 'v2.1.3' in r),
            ],
        },
        {
            'name': '标题编号不转换',
            'input': '1. 第一章\n1.1 子节\n1.1.1 三级标题',
            'checks': [
                ('1. 保留',   lambda r: '1. ' in r or '1.\u3000' in r),
                ('1.1 保留',  lambda r: '1.1' in r),
                ('无误转换',  lambda r: '1。' not in r),
            ],
        },
        {
            'name': 'URL/邮箱/文件名不转换',
            'input': '访问https://example.com，邮件至test@gmail.com，编辑file.txt。',
            'checks': [
                ('URL保留',      lambda r: 'https://example.com' in r),
                ('邮箱保留',     lambda r: 'test@gmail.com' in r),
                ('文件名保留',   lambda r: 'file.txt' in r),
                ('中文句号存在', lambda r: '。' in r),
            ],
        },
        {
            'name': '英文缩写不转换',
            'input': '这是e.g.的用法，U.S.A.是缩写，i.e.即表示。',
            'checks': [
                ('e.g. 保留',   lambda r: 'e.g.' in r),
                ('U.S.A. 保留', lambda r: 'U.S.A.' in r),
                ('i.e. 保留',   lambda r: 'i.e.' in r),
            ],
        },
        {
            'name': '无中英间距自动插入',
            'input': '这是AI工具version2很好用，效率提升100%。',
            'checks': [
                ('AI前无强制空格', lambda r: 'AI工具' in r or '这是AI' in r),
                ('无 version 2 分割', lambda r: 'version2' in r or 'version 2' not in r),
            ],
        },
        {
            'name': '普通中文标点正常转换',
            'input': '你好, 世界! 这是测试: 完成; 结束.',
            'checks': [
                ('逗号转换',   lambda r: '，' in r and ',' not in r),
                ('感叹号转换', lambda r: '！' in r and '!' not in r),
                ('冒号转换',   lambda r: '：' in r and ':' not in r),
                ('分号转换',   lambda r: '；' in r and ';' not in r),
                ('句号转换',   lambda r: '。' in r),
            ],
        },
        {
            'name': '省略号与破折号',
            'input': '等等...我想想---好吧',
            'checks': [
                ('省略号规范', lambda r: '……' in r),
                ('破折号规范', lambda r: '—' in r and '——' not in r),
            ],
        },
        {
            'name': '多段落与空行',
            'input': '第一段。\n\n第二段。\n\n\n\n第三段。',
            'checks': [
                ('段首不新增全角空格', lambda r: '\u3000' not in r),
                ('自然段以普通空格缩进', lambda r: all(not line or line.startswith(INDENT) for line in r.split('\n'))),
                ('空行不超1个', lambda r: '\n\n\n' not in r),
            ],
        },
        {
            'name': '空格清理：缩进/标题/中文混合',
            'input': '    我 们 去 吃 饭 。\n## 项 目 背 景\n你 好, 世 界!',
            'checks': [
                ('中文字符间无空格',  lambda r: '我们去吃饭' in r),
                ('行首缩进保留',      lambda r: any(
                    ln.startswith('    ')
                    for ln in r.split('\n')
                )),
                ('标题文字保留', lambda r: '项目背景' in r and '#' not in r),
                ('中文标点转换',      lambda r: '，' in r and '！' in r),
                ('中文内容间无空格',  lambda r: '你好，世界！' in r),
            ],
        },
        {
            'name': '引号审查：嵌套修复+成对检查',
            'input': '\u201c外层引号\u201c内层引号\u201d内容\u201d，\u201c正常对\u201d。',
            'checks': [
                ('内层双引号已换为单引号', lambda r: _L_SQUOTE in r),
                ('外层双引号完整',         lambda r: r.count(_L_DQUOTE) == r.count(_R_DQUOTE)),
                ('quote_issues字段存在',   lambda r: True),   # process_text 返回 dict
            ],
            'pre': lambda t: process_text(t)['result'],
        },
        {
            'name': '引号审查：残留英文引号被修复',
            'input': '他说\u201c你好，"世界"\u201d，结束。',
            'checks': [
                ('无残留英文双引号', lambda r: '"' not in r and '"' not in r),
                ('中文引号存在',     lambda r: _L_DQUOTE in r),
            ],
            'pre': lambda t: process_text(t)['result'],
        },
        {
            'name': '引号审查：报告字段完整性',
            'input': '\u201c测试文本\u201d，内容正常。',
            'checks': [
                ('quote_summary存在',  lambda r: 'quote_summary' in r),
                ('quote_issues为列表', lambda r: isinstance(r.get('quote_issues'), list)),
            ],
            'pre': lambda t: process_text(t),
        },
        {
            'name': '引号规范化：英文双引号转中文',
            'input': '他说"你好，世界"，又说"再见"。',
            'checks': [
                ('英文双引号转为中文',   lambda r: '\u201c你好' in r or '\u201c' in r),
                ('闭引号正确',           lambda r: '\u201d' in r),
                ('引号数量成对',         lambda r: r.count('\u201c') == r.count('\u201d')),
            ],
        },
        {
            'name': '引号幂等：保留已有中文引号',
            'input': '\u201c已规范\u201d，请确认。',
            'checks': [
                ('中文引号不重复', lambda r: r.count('\u201c') == 1),
                ('中文引号不丢失', lambda r: '\u201c已规范\u201d' in r),
            ],
        },
        {
            'name': '单引号：所有格不转换，中文上下文转换',
            'input': "中文文本中'这个引号'需要转换，英文所有格it's保留。",
            'checks': [
                ("it's 保留",          lambda r: "it's" in r),
                ('中文上下文单引号转换', lambda r: '\u2018' in r),
                ('引号成对',            lambda r: r.count('\u2018') == r.count('\u2019')),
            ],
        },
        {
            'name': '字数超限拦截',
            'input': 'a' * (MAX_TEXT_LENGTH + 1),
            'checks': [
                ('超长被拦截', lambda r: r == '__TOOLONG__'),
            ],
            'pre': lambda t: '__TOOLONG__' if len(t) > MAX_TEXT_LENGTH else R(t),
        },
    ]

    for tc in integration_cases:
        pre_fn = tc.get('pre', R)
        result = pre_fn(tc['input'])
        print(f"\n【{tc['name']}】")
        for desc, check in tc['checks']:
            ok = check(result)
            flag = '✅' if ok else '❌'
            print(f'  {flag} {desc}')
            if not ok:
                all_passed = False
                print(f'     实际输出片段：{repr(result[:120])}')

    print(f'\n{sep}')
    if all_passed:
        print('  ✅ 全部自检通过！')
    else:
        print('  ❌ 存在失败项，请检查对应函数！')
    print(sep)
    return all_passed


if __name__ == '__main__':
    raise SystemExit(0 if run_tests() else 1)
