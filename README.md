# 标点转换器

一个将英文标点转换为中文标点的网页工具，包含标点转换、引号审查、段首缩进、空格清理和常见特殊文本保护规则。

## 在线部署

本项目已经改造成 GitHub Pages 可直接托管的静态站点：

- 入口文件：`index.html`
- 转换逻辑：浏览器通过 Pyodide 加载并运行 `utils.py`
- 发布方式：GitHub Pages，`main` 分支根目录

新建公开仓库 `punctuation-converter` 并推送后，最终访问地址通常是：

```text
https://<你的GitHub用户名>.github.io/punctuation-converter/
```

## 本地静态预览

不要直接双击打开 `index.html`，因为浏览器会限制本地 `fetch("utils.py")`。请在项目根目录启动一个本地静态服务器：

```powershell
python -m http.server 8000
```

然后访问：

```text
http://127.0.0.1:8000/
```

首次打开会加载 Pyodide，可能需要等待几秒。页面显示“转换引擎加载完成”后即可使用。

## 保留的 Flask 本地版本

原来的 Flask 版本仍然保留：

```powershell
python app.py
```

然后访问：

```text
http://127.0.0.1:5000/
```

GitHub Pages 不会运行 Flask 后端，线上页面使用根目录 `index.html`。

## GitHub Pages 发布步骤

1. 在 GitHub 新建公开仓库：`punctuation-converter`。
2. 在本地项目目录初始化 Git 并提交代码。
3. 添加远程仓库并推送到 `main` 分支。
4. 在仓库 Settings -> Pages 中选择：Deploy from a branch，Branch 选择 `main`，Folder 选择 `/ (root)`。
5. 等待 Pages 构建完成后访问生成的 `github.io` 链接。

## 自检测试

运行 Python 版自检：

```powershell
$env:PYTHONIOENCODING='utf-8'; python -B utils.py
```

全部 PASS 表示核心转换逻辑正常。