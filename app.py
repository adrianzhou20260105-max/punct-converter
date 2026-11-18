# app.py
# 中文排版工具 - Flask Web 应用入口（v3）

from flask import Flask, render_template, request, jsonify
from utils import process_text, get_punct_map, MAX_TEXT_LENGTH

app = Flask(__name__, template_folder=".")


@app.route("/")
def index():
    """渲染主页"""
    return render_template("index.html", engine="flask")


@app.route("/convert", methods=["POST"])
def convert():
    """
    接收前端 JSON 请求，按完整流程处理文本并返回结果。
    请求体：{ "text": "原始文本" }
    响应体：{
        "result":          最终文本,
        "count":           替换的英文标点数,
        "indent_lines":    缩进段落数（兼容字段，现为 0）,
        "quote_issues":    引号审查问题列表（list[dict]），空表示无问题,
        "quote_summary":   引号审查摘要（字符串），供前端气泡/提示展示,
        "quote_fixed":     自动修复的问题数量（int）,
        "max_length":      最大允许字符数（供前端参考）
    }
    """
    data = request.get_json(silent=True)
    if not data or "text" not in data:
        return jsonify({"error": "请提供 text 字段"}), 400

    original = data["text"]

    # 字数限制校验（后端）
    if len(original) > MAX_TEXT_LENGTH:
        return jsonify({
            "error": f"文本长度超过限制（最多 {MAX_TEXT_LENGTH} 字符，当前 {len(original)} 字符）"
        }), 400

    output = process_text(original)

    # 统计自动修复的问题数（severity == FIXED）
    fixed_count = sum(
        1 for iss in output["quote_issues"]
        if iss.get("severity") == "FIXED"
    )

    return jsonify({
        "result":        output["result"],
        "count":         output["punct_count"],
        "indent_lines":  output["indent_lines"],
        "quote_issues":  output["quote_issues"],
        "quote_summary": output["quote_summary"],
        "quote_fixed":   fixed_count,
        "max_length":    MAX_TEXT_LENGTH,
    })


@app.route("/map", methods=["GET"])
def punct_map_view():
    """返回当前标点映射表（供前端展示对照表）"""
    return jsonify(get_punct_map())


if __name__ == "__main__":
    print("🚀 中文排版工具已启动")
    print(f"📌 访问地址：http://127.0.0.1:5000")
    print(f"📝 最大输入：{MAX_TEXT_LENGTH} 字符")
    app.run(debug=True, host="0.0.0.0", port=5000)
