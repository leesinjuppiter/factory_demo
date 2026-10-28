"""将交付 Markdown 合成为本地可直接打开的中文说明书，无外部网络资源。"""
from pathlib import Path
import re
import markdown

ROOT = Path(__file__).resolve().parents[1]
documents = [("readme", "开始使用", ROOT / "README.md"),
             ("product", "产品需求与边界", ROOT / "docs/PRODUCT.md"),
             ("architecture", "架构与代码说明", ROOT / "docs/ARCHITECTURE.md"),
             ("contract", "API 协议", ROOT / "docs/CONTRACT.md"),
             ("inference", "推理模块", ROOT / "docs/INFERENCE.md"),
             ("performance", "性能测试指南", ROOT / "docs/PERFORMANCE.md"),
             ("verification", "本次验收报告", ROOT / "docs/VERIFICATION.md")]
nav, sections = [], []
for key, title, path in documents:
    if not path.exists():
        continue
    source = path.read_text(encoding="utf-8")
    html = markdown.markdown(source, extensions=["tables", "fenced_code"])
    # README 相对链接以项目根为起点，合并后从 docs/ 解析。
    if key == "readme":
        html = re.sub(r'href="(?!https?://|#)([^\"]+)"', lambda m: 'href="../' + m.group(1) + '"', html)
    nav.append(f'<a href="#{key}">{title}</a>')
    sections.append(f'<section id="{key}">{html}</section>')
style = """*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:#f4f6f5;color:#233331;font:16px/1.8 'Microsoft YaHei',sans-serif}aside{position:fixed;inset:0 auto 0 0;width:245px;padding:28px 20px;background:#183332;color:white}aside h1{font-size:23px;margin:0 0 8px}aside p{font-size:13px;color:#bfceca}aside a{display:block;padding:9px 12px;color:white;text-decoration:none;border-left:3px solid transparent}aside a:hover{background:#2d4c46;border-left-color:#96d6bb}main{margin-left:245px;max-width:1250px;padding:36px}section{background:white;border:1px solid #d9e3dd;padding:30px 38px;margin-bottom:28px;scroll-margin-top:20px}h1{font-size:28px}h2{font-size:22px;border-bottom:1px solid #dce7e0;padding-bottom:8px;margin-top:36px}h3{font-size:18px;color:#267764}a{color:#16765e}table{border-collapse:collapse;width:100%;font-size:14px;display:block;overflow:auto}th,td{padding:9px 12px;border:1px solid #d9e3dd;text-align:left}th{background:#eef5f1}code{font-family:Consolas,monospace;font-size:.9em;overflow-wrap:anywhere;background:#edf3ef;padding:2px 4px}pre{padding:18px;background:#edf3ef;overflow:auto;line-height:1.6}pre code{padding:0}p,li{overflow-wrap:anywhere}img{max-width:100%}@media(max-width:800px){aside{position:static;width:100%}aside a{display:inline-block}main{margin:0;padding:12px}section{padding:18px}h1{font-size:23px}}@media print{aside{display:none}main{margin:0;padding:0}section{border:0;break-before:page}a{color:inherit}}"""
output = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Factory Demo · 产品与代码说明书</title><style>' + style + '</style><body><aside><h1>FACTORY DEMO</h1><p>产品与代码说明书 · V1.0<br>2026-10-28 / 本机版本</p>' + ''.join(nav) + '</aside><main>' + ''.join(sections) + '</main></body></html>'
path = ROOT / "docs/GUIDE.html"
path.write_text(output, encoding="utf-8")
print(path)
