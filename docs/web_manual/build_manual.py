"""Build the offline documentation reader, diagrams and source manifest only.

Run with yolo_v5_obb Python -B; requires the already available Markdown package.
Does not import the backend, query PostgreSQL, or start inference.
"""
import base64
import hashlib
import html
import json
import os
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit
import markdown

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
DOC = ROOT / 'docs'
DIAGS = OUT / 'diagrams'
DIAGS.mkdir(exist_ok=True)
C = {'paper': '#f2f4f3', 'ink': '#203039', 'muted': '#52676b', 'accent': '#177b68', 'link': '#2e5aa8', 'tint': '#edf5f1'}
FONT = "'Segoe UI','Microsoft YaHei',sans-serif"
MONO = "Consolas,'Microsoft YaHei',monospace"
MAP = []

def esc(s): return html.escape(str(s), quote=True)

def text(x, y, value, size=16, fill='ink', anchor='middle', mono=False, weight=400):
    return f'<text x="{x}" y="{y}" fill="{C[fill]}" font-family="{MONO if mono else FONT}" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}">{esc(value)}</text>'

def node(x, y, w, h, title, sub, focal=False, kind='box'):
    stroke = C['accent' if focal else 'muted']
    fill = C['tint' if focal else 'paper']
    shape = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>'
    if kind == 'db':
        shape += f'<path d="M {x},{y+16} Q {x+w/2},{y+36} {x+w},{y+16}" fill="none" stroke="{stroke}"/>'
    return f'<g class="node" data-node-label="{esc(title)}">{shape}{text(x+w/2,y+36,title,weight=600)}{text(x+w/2,y+60,sub,12,mono=True)}</g>'

def label(x, y, value, fill='muted', anchor='middle'):
    width = sum(12 if ord(ch)>127 else 7.2 for ch in value) + 16
    left = x-width/2 if anchor=='middle' else x-8
    return f'<g class="edge-label"><rect x="{left}" y="{y-15}" width="{width}" height="22" fill="{C["paper"]}"/>{text(x,y,value,12,fill,anchor,True)}</g>'

def arrow(slug, path, color='muted', dashed=False, lab=None):
    d = ' stroke-dasharray="5,4"' if dashed else ''
    s = f'<path class="connector" d="{path}" fill="none" stroke="{C[color]}" stroke-width="1.6"{d} marker-end="url(#{slug}-{color})"/>'
    return s + (label(*lab, fill=color) if lab else '')

def svg(slug, title, desc, content, legend='实线：调用 / 写入　　虚线：结果返回　　绿色：重点处理边界'):
    defs = ''.join(f'<marker id="{slug}-{k}" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon points="0 0,8 3,0 6" fill="{C[k]}"/></marker>' for k in ['muted','accent','link'])
    return f'<svg viewBox="0 0 1280 720" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="{slug}-title {slug}-desc"><title id="{slug}-title">{esc(title)}</title><desc id="{slug}-desc">{esc(desc)}</desc><defs>{defs}</defs><rect x="0" y="0" width="1280" height="720" fill="{C["paper"]}"/>{content}<line x1="40" y1="660" x2="1240" y2="660" stroke="#c4d0cb"/>{text(40,692,legend,12,"muted","start")}</svg>'

DIAGRAM_CSS = '''*{box-sizing:border-box}body{margin:0;padding:24px;background:#f2f4f3;color:#203039;font:16px/1.8 'Segoe UI','Microsoft YaHei',sans-serif}.frame{max-width:1380px;min-width:0;margin:auto}h1{font-size:28px;margin:0 0 12px}p{margin:8px 0 16px;color:#52676b}.diagram-container{width:100%;overflow-x:auto;border:1px solid #cbd7d1}svg{display:block;width:100%;min-width:1280px}footer{margin-top:18px;font-size:13px;color:#52676b}@media print{body{padding:0}.diagram-container{overflow-x:visible}svg{min-width:0}}'''

def save_diagram(slug, title, desc, content, nodes, edges, legend=None):
    figure = svg(slug,title,desc,content,**({'legend':legend} if legend else {}))
    page = f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title><style>{DIAGRAM_CSS}</style></head><body><div class="frame"><h1>{title}</h1><p>{desc}</p><div class="diagram-container">{figure}</div><footer>Factory Demo v1.3 · 实际代码路径 · 2026-10-28。窄屏可在图内横向滚动。详细异常分支见阅读手册。</footer></div></body></html>'
    (DIAGS/f'{slug}.html').write_text(page,encoding='utf-8')
    MAP.append({'id':slug,'title':title,'description':desc,'nodes':nodes,'edges':edges})
    return figure

FIGURES = {}
s = '01-architecture'
a = ''
a += arrow(s,'M 272,148 H 368','link',lab=(320,130,'WS / HTTP'))
a += arrow(s,'M 592,148 H 688',lab=(640,130,'订阅 / 快照'))
a += arrow(s,'M 912,132 H 1008',lab=(960,114,'预览任务'))
a += arrow(s,'M 1008,168 H 912',dashed=True,lab=(960,202,'JPEG / URL'))
a += arrow(s,'M 832,392 V 192',lab=(900,316,'提交后发布'))
a += arrow(s,'M 688,436 H 592',lab=(640,416,'事务保存'))
a += arrow(s,'M 912,420 H 1008',lab=(960,400,'BGR'))
a += arrow(s,'M 1008,456 H 912',dashed=True,lab=(960,490,'检测结果'))
a += arrow(s,'M 272,436 H 312 Q 320,436 320,428 V 248 Q 320,240 328,240 H 392 Q 400,240 400,232 V 192','link')
for args in [(48,104,224,88,'只读展示','stream / 纯画布'),(368,104,224,88,'FastAPI 路由','管理HTTP / 展示WS'),(688,104,224,88,'展示服务','快照 / 有界订阅',True),(1008,104,224,88,'预览线程 / 缓存','1024宽 / JPEG / UUID'),(48,392,224,88,'后台管理','配置 / 控制 / 历史'),(368,392,224,88,'PostgreSQL','Run / Frame JSONB',False,'db'),(688,392,224,88,'Runner','来源 / 状态 / 保存'),(1008,392,224,88,'推理适配器','真实PyTorch / 能力')]: a += node(*args)
a += text(48,64,'同一后端进程内的职责分工：推理与预览分别工作，展示订阅不启动生产。',16,'muted','start')
a += text(48,548,'来源：有限目录 / 上传，或完成发布的持续 inbox；原图快照仍由 Runner 保存。',16,'ink','start')
a += text(48,584,'管理配置和历史数据库查询在总图省略；没有异步归档或真实执行设备。',16,'muted','start')
FIGURES[s] = save_diagram(s,'01 · V1.3 系统职责与展示支路','单机模块化：数据库提交后发布结果，预览编码与浏览器发送独立于推理线程。',a,
    ['Display','FastAPI','Presentation','PreviewWorker','Admin','PostgreSQL','Runner','Inference'],
    [{'from':x,'to':y,'payload':v} for x,y,v in [('Display','FastAPI','display WS / preview HTTP'),('FastAPI','Presentation','subscribe/snapshot'),('Presentation','PreviewWorker','bounded latest pending'),('PreviewWorker','Presentation','JPEG cache / immutable URL'),('Runner','Presentation','committed frame'),('Runner','PostgreSQL','Frame + Run transaction'),('Runner','Inference','BGR'),('Inference','Runner','detections'),('Admin','FastAPI','management HTTP')]])

def vertical(slug,title,desc,rows,note):
    parts = ''
    for i in range(5): parts += arrow(slug,f'M 504,{140+i*96} V {164+i*96}')
    for i,(name,sub,payload) in enumerate(rows):
        parts += node(264,68+i*96,480,72,name,sub,focal=i==4)
        parts += text(792,100+i*96,payload,12,'muted','start',mono=True)
    parts += text(40,636,note,12,'muted','start')
    return save_diagram(slug,title,desc,parts,[{'id':i+1,'name':r[0],'operation':r[1],'output':r[2]} for i,r in enumerate(rows)],[{'from':i,'to':i+1,'payload':rows[i-1][2]} for i in range(1,6)],'实线：顺序处理　　右侧：该步产生的数据　　绿色：关键转换或持久化边界')

FIGURES['02-frame-pipeline'] = vertical('02-frame-pipeline','02 · 单帧处理与提交','展示单张合法图片的主路径；读图错误、模型失败与暂停停止的分支见图下说明。',[
('F1 · 读取、校验、解码','runner._frame / images.decode','BGR [H,W,3] + 原始字节'),
('F2 · 固化原图并计算哈希','write_bytes / SHA-256','image_path + sha256'),
('F3 · 调用 OBB 适配器','adapter.predict(image, params)','detections + timing_ms'),
('F4 · 组装帧与运行汇总','Frame / updated Run','Frame + Run + image_path'),
('F5 · 同一数据库事务提交','Store.save_frame','INSERT Frame + UPSERT Run'),
('F6 · 发布内存结果与预览任务','内存快照 / Presentation.update','状态可读 → 异步预览 → WS')],
'快照文件先写入；文件与数据库并非同一个原子事务。提交失败不能发布为成功结果。')

FIGURES['03-inference-transform'] = vertical('03-inference-transform','03 · 推理数据形态转换','输入层交付 BGR 原图；适配器返回原图像素四点框；前端不接触模型候选张量。',[
('I1 · 接收解码原图','uint8 / BGR','[H,W,3]'),
('I2 · letterbox 与张量化','BGR→RGB / HWC→CHW / ÷255','FP32 [1,3,H\u2032,W\u2032]'),
('I3 · PyTorch 模型前向','CPU / inference_mode','[1,N,193] = [1,N,5+8+180]'),
('I4 · 旋转候选筛选','CSL-180 / multi-label rotated NMS','旋转框 + 置信度 + 类别'),
('I5 · 四点与原图坐标恢复','rbox2poly / scale_polys','每目标四点，原图像素坐标'),
('I6 · 输出公共检测协议','class_id / confidence / polygon','detections + 三阶段 timing_ms')],
'H\u2032/W\u2032 随 letterbox 结果变化；N 不写死。模型 8 类与数据集 7 类的编号不能直接比较。')

s='04-display-sequence'
xs=[128,448,768,1120]
a=''
for x in xs: a+=f'<line x1="{x}" y1="144" x2="{x}" y2="624" stroke="#9caaa4" stroke-dasharray="4,4"/>'
messages=[(0,1,184,'1 WS订阅',False),(1,0,228,'2 结果待预览',True),(1,2,272,'3 预览任务',False),(2,3,316,'4 缓存JPEG',False),(2,1,360,'5 预览引用',True),(1,0,404,'6 完整快照',True),(0,3,480,'7 GET预览URL',False),(3,0,548,'8 JPEG字节',True)]
for i,j,y,l,ret in messages:
    a+=arrow(s,f'M {xs[i]},{y} H {xs[j]}','link' if i==0 or j==0 else 'muted',ret,((xs[i]+xs[j])/2,y-16,l))
for x,n,sub in zip(xs,['浏览器stream','展示服务','预览工作线程','受控HTTP缓存'],['配对 / 解码','内存状态 / WS','缩放 / JPEG','不可变URL / 有界']): a+=node(x-104,56,208,88,n,sub)
a+=text(40,612,'解码完成且身份/连接代次仍有效 → 原子提交图片与框 → 纯画布、坐标与详情。',12,'muted','start')
a+=text(40,636,'这里不查询数据库；输入结果已由 Runner 提交。缓存过期返回410，旧图不能配新框。',12,'muted','start')
FIGURES[s]=save_diagram(s,'04 · WS快照、预览与同帧显示','先有结果再生成预览；浏览器读取不可变图片引用。时序表示逻辑先后，不是实测耗时比例。',a,
['Browser stream','Presentation','PreviewWorker','HTTP cache'],[{'from':['Browser stream','Presentation','PreviewWorker','HTTP cache'][i],'to':['Browser stream','Presentation','PreviewWorker','HTTP cache'][j],'message':l,'return':ret} for i,j,y,l,ret in messages],
'实线：订阅 / 工作 / 请求　　虚线：结果返回　　配置控制与历史读取不在此路径')

s='05-history-export'
a=''
a+=arrow(s,'M 280,168 H 456','link',lab=(368,148,'GET 历史'))
a+=arrow(s,'M 760,152 H 1000',lab=(880,132,'读取记录'))
a+=arrow(s,'M 1000,192 H 760',dashed=True,lab=(880,226,'Run / Frames'))
a+=arrow(s,'M 608,232 V 440',lab=(684,340,'按类型生成'))
a+=arrow(s,'M 1120,232 V 440',lab=(1184,340,'路径字段'))
a+=arrow(s,'M 1000,484 H 760',lab=(880,464,'数据库路径'))
a+=arrow(s,'M 456,484 H 280','link',True,lab=(368,464,'JSON/CSV/PNG'))
a+=arrow(s,'M 160,440 V 232','link',True,lab=(232,340,'下载 / 显示'))
for args in [(48,104,232,128,'历史页面','run_id / frame_id'),(456,104,304,128,'历史与导出 API','backend/app.py',True),(1000,104,232,128,'PostgreSQL','已保存 Run / Frames',False,'db'),(1000,440,232,88,'image_path','来自 Frame 记录'),(456,440,304,88,'读取 / 格式化 / 绘图','JSON / CSV / 原图 / PNG'),(48,440,232,88,'HTTP 响应','供浏览器读取')]:a+=node(*args)
a+=text(48,592,'此路径不调用适配器、不重新推理；绘框 PNG 使用已保存框进行渲染。',16,'ink','start')
FIGURES[s]=save_diagram(s,'05 · 历史读取与导出','历史记录从数据库读取，图片从原始快照读取；导出预测结果与标注功能是不同的职责。',a,
['History UI','History API','PostgreSQL','image_path','format/render','HTTP response'],
[{'from':x,'to':y,'payload':p} for x,y,p in [('History UI','History API','run_id/frame_id'),('History API','PostgreSQL','queries'),('PostgreSQL','History API','Run/Frames including image_path'),('PostgreSQL','image_path','field in saved Frame'),('History API','format/render','records and route choice'),('image_path','format/render','path used to read snapshot file bytes'),('format/render','HTTP response','JSON/CSV/image/PNG'),('HTTP response','History UI','download/display')]])
(DIAGS/'flow-map.json').write_text(json.dumps(MAP,ensure_ascii=False,indent=2),encoding='utf-8')

DOCS=[('cloud','云端GPU部署',DOC/'CLOUD_DEPLOYMENT.md'),('release','V1.3 当前实现',DOC/'V1_3_DECOUPLING.md'),('status','文档状态索引',DOC/'DOCUMENT_STATUS.md'),('camera','落盘来源与模拟',DOC/'CAMERA_INBOX.md'),('industrial','工业展示说明',DOC/'INDUSTRIAL_DISPLAY.md'),('modules','展示与后台分离',DOC/'MODULE_SPLIT.md'),('start','开始使用',ROOT/'README.md'),('flow','数据流图解',DOC/'DATA_FLOW_GUIDE.md'),('product','产品需求与边界',DOC/'PRODUCT.md'),('architecture','架构与代码说明',DOC/'ARCHITECTURE.md'),('contract','API 与数据协议',DOC/'CONTRACT.md'),('inference','推理模块说明',DOC/'INFERENCE.md'),('performance','性能测试指南',DOC/'PERFORMANCE.md'),('analysis','性能优化分析',DOC/'PERFORMANCE_OPTIMIZATION_ANALYSIS_20261028.md'),('verification','已有验收记录',DOC/'VERIFICATION.md')]

def slugify(value, separator):
    value=re.sub(r'[^\w\s-]','',value.lower()).strip()
    return re.sub(r'[-\s]+',separator,value)

converted={}; heads={}; source_map={str(p.resolve()):key for key,_,p in DOCS}
manifest=[]
for key,title,path in DOCS:
    source=path.read_text(encoding='utf-8')
    md=markdown.Markdown(extensions=['tables','fenced_code','toc'],extension_configs={'toc':{'slugify':slugify,'toc_depth':'2-3'}})
    body=md.convert(source)
    ids=re.findall(r'<h[1-6] id="([^"]+)"',body)
    heads[key]=ids
    body=re.sub(r'id="([^"]+)"',lambda m:f'id="{key}-{m[1]}"',body)
    converted[key]=(body,path)
    manifest.append({'section':key,'source':str(path.relative_to(ROOT)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'headings':len(ids)})

def links(body,path,key):
    def repl(m):
        attr,target=m[1],html.unescape(m[2]); parsed=urlsplit(target)
        if parsed.scheme or target.startswith('//'): return m[0]
        if target.startswith('#'): return f'{attr}="#{key}-{esc(unquote(target[1:]))}"'
        dest=(path.parent/unquote(parsed.path)).resolve()
        if str(dest) in source_map:
            k=source_map[str(dest)]; frag=unquote(parsed.fragment)
            anchor=f'{k}-{frag}' if frag in heads[k] else k
            return f'{attr}="#{esc(anchor)}"'
        if dest == DOC/'GUIDE.html': return f'{attr}="#home"'
        if attr=='src' and dest.suffix.lower() in ['.png','.jpg','.jpeg'] and dest.exists():
            mime='image/png' if dest.suffix.lower()=='.png' else 'image/jpeg'
            return f'src="data:{mime};base64,{base64.b64encode(dest.read_bytes()).decode()}"'
        relative=Path(os.path.relpath(dest,OUT)).as_posix()
        return f'{attr}="{esc(relative)}{("#"+esc(parsed.fragment)) if parsed.fragment else ""}"'
    return re.sub(r'(href|src)="([^"]+)"',repl,body)

sections=[]; nav=[]; search=[]
for key,title,path in DOCS:
    body,_=converted[key]
    body=links(body,path,key)
    for slug,figure in FIGURES.items():
        body=body.replace(f'<!-- DIAGRAM:{slug} -->',f'<figure class="diagram"><div class="diagram-container" tabindex="0" aria-label="可横向滚动的流程图">{figure}</div><figcaption>图可在窄屏内横向滚动；下方表格给出载荷和代码定位。</figcaption></figure>')
    if key=='inference':
        body=body.replace('任务层单独记录读图与完整处理耗时。','任务层记录读图与四阶段处理合计；该合计不包含完整端到端成本。')
    headings=re.findall(r'<h([23]) id="([^"]+)">(.*?)</h\1>',body,re.S)
    entries=''.join(f'<a href="#{ident}" class="sub level-{level}">{re.sub("<[^>]+>","",name)}</a>' for level,ident,name in headings)
    nav.append(f'<details class="nav-group" data-key="{key}"><summary><a href="#{key}">{esc(title)}</a></summary>{entries}</details>')
    sections.append(f'<section class="chapter" id="{key}"><div class="chapter-meta">{esc(title)} · 来源 {esc(str(path.relative_to(ROOT)))}</div>{body}</section>')
    chunks=re.split(r'(?=<h[123] id=)',body)
    for chunk in chunks:
        hit=re.search(r'<h[123] id="([^"]+)">(.*?)</h[123]>',chunk,re.S)
        if hit:
            plain=html.unescape(re.sub(r'<[^>]+>',' ',chunk));plain=re.sub(r'\s+',' ',plain).strip()
            search.append({'id':hit[1],'title':html.unescape(re.sub('<[^>]+>','',hit[2])),'chapter':title,'text':plain})

css='''
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:26px}body{margin:0;background:#f2f4f3;color:#203039;font:16px/1.9 'Segoe UI','Microsoft YaHei',sans-serif}a{color:#126a59;text-underline-offset:3px}button,input{font:inherit}button{cursor:pointer}a:focus-visible,button:focus-visible,summary:focus-visible,input:focus-visible,.diagram-container:focus-visible{outline:3px solid #177b68;outline-offset:3px}
.sidebar{position:fixed;inset:0 auto 0 0;width:292px;padding:26px 20px;background:#152d32;color:#edf5f1;overflow-y:auto}.brand{font-size:24px;font-weight:750;letter-spacing:.04em}.sidebar p{font-size:13px;color:#c1d5ce;margin:5px 0 18px}.sidebar a{color:#e7f2ed;text-decoration:none}.top-link{display:block;margin:12px 0;padding:6px 10px;border-left:3px solid #75ba9c}.nav-group{border-top:1px solid #375055;padding:6px 0}.nav-group summary{cursor:pointer;padding:5px 0;font-size:15px}.nav-group .sub{display:block;padding:5px 10px;font-size:12px;line-height:1.5;border-left:2px solid transparent}.nav-group .level-3{padding-left:18px;color:#c1d5ce}.nav-group a:hover,.nav-group a.active{background:#28464a;border-left-color:#75ba9c}.searchbox{width:100%;border:1px solid #708a83;border-radius:6px;padding:9px 10px;background:#fff;color:#203039;font-size:14px}.search-help{font-size:12px!important}
main{margin-left:292px;max-width:1820px;padding:30px 36px 70px;min-width:0}.hero{padding:24px 0 32px;border-bottom:2px solid #177b68;margin-bottom:28px}.eyebrow{font:12px Consolas,monospace;letter-spacing:.15em;color:#52676b}.hero h1{font-size:36px;margin:10px 0;line-height:1.4}.hero .lead{max-width:900px;font-size:18px;color:#52676b}.badge{display:inline-block;border:1px solid #abc5b7;border-radius:4px;background:#edf5f1;padding:2px 9px;font-size:12px;margin:4px 8px 4px 0}.route{padding:16px 20px;background:#fff;border-left:4px solid #177b68;margin-top:22px}.route a{margin-right:14px}.toolbar{display:flex;gap:10px;flex-wrap:wrap;margin:16px 0}.toolbar button,.tool-link{border:1px solid #b6c8c0;border-radius:5px;padding:7px 12px;background:white;color:#203039;text-decoration:none;font-size:14px}.chapter{background:white;border:1px solid #d6e1da;padding:30px 36px;margin-bottom:28px;min-width:0;overflow-wrap:anywhere}.chapter-meta{font-size:12px;color:#52676b;border-bottom:1px solid #e0e7e3;padding-bottom:12px;margin-bottom:20px}.chapter h1{font-size:28px;line-height:1.5;margin:8px 0 24px}.chapter h2{font-size:22px;margin:36px 0 16px;border-top:1px solid #dfe5e3;padding-top:22px}.chapter h3{font-size:18px;margin:28px 0 12px;color:#126a59}p{margin:14px 0}li{margin:7px 0}pre{padding:18px;background:#edf5f1;border:1px solid #d7e6dc;overflow:auto;position:relative;font-size:14px;line-height:1.7}code{font-family:Consolas,'Microsoft YaHei',monospace;background:#edf5f1;padding:2px 4px;font-size:.9em;overflow-wrap:anywhere}pre code{padding:0;white-space:pre;overflow-wrap:normal}.copy{display:block;margin:4px 0 0 auto;border:1px solid #a6bfb2;background:#fff;color:#126a59;border-radius:4px;padding:3px 9px;font-size:12px}
table{display:block;width:100%;overflow-x:auto;border-collapse:collapse;font-size:14px;line-height:1.8;margin:18px 0}th,td{padding:10px 12px;border:1px solid #d6e1da;min-width:100px;vertical-align:top;text-align:left}th{background:#edf5f1}tbody tr:nth-child(even){background:#fafcfb}img{max-width:100%;height:auto;border:1px solid #d6e1da}.diagram{margin:24px 0;background:#f2f4f3}.diagram-container{width:100%;overflow-x:auto;border:1px solid #cbd7d1}.diagram svg{display:block;width:100%;min-width:1280px}.diagram figcaption{font-size:12px;color:#52676b;padding:6px 10px}.results{background:#fff;border:1px solid #cbd7d1;padding:22px;margin-bottom:25px}.results[hidden]{display:none}.result{display:block;border-bottom:1px solid #e0e7e3;padding:12px 0;text-decoration:none}.result strong{display:block}.result small{display:block;color:#52676b;font-size:13px}.results h2{margin:0}.note{font-size:13px;color:#52676b}footer{font-size:13px;color:#52676b}.backtop{position:fixed;bottom:20px;right:20px;padding:8px 12px;background:#152d32;color:#fff;border-radius:5px;text-decoration:none;font-size:12px}.status{min-height:24px;color:#126a59;font-size:13px}
@media(max-width:1050px){.sidebar{position:static;width:auto;padding:20px}.sidebar nav{max-height:260px;overflow:auto}.sidebar p{margin-bottom:10px}main{margin-left:0;padding:20px}.hero h1{font-size:30px}.chapter{padding:24px}.brand{font-size:22px}}
@media(max-width:560px){main{padding:12px}.chapter{padding:18px 14px}.hero h1{font-size:27px}.chapter h1{font-size:24px}.chapter h2{font-size:21px}body{font-size:15px}.backtop{bottom:10px;right:10px}.hero .lead{font-size:16px}}
@media print{html{scroll-behavior:auto}body{background:white;font-size:10.5pt}.sidebar,.toolbar,.backtop,.results,.copy{display:none}main{margin:0;max-width:none;padding:0}.hero{break-after:page}.chapter{border:0;padding:0;break-before:page}.chapter h2,.chapter h3{break-after:avoid}.diagram-container{overflow-x:visible}.diagram svg{min-width:0}.diagram{break-inside:avoid}table{display:table;font-size:9pt}th,td{min-width:0;padding:5px}pre{white-space:pre-wrap}pre code{white-space:pre-wrap}a{color:#203039}}
'''
script='''
const index=JSON.parse(document.querySelector('#search-index').textContent), q=document.querySelector('#query'), results=document.querySelector('#results');
function search(){const value=q.value.trim().toLowerCase();results.replaceChildren();results.hidden=!value;if(!value){document.querySelector("#search-status").textContent="";return;}const words=value.split(/\\s+/);const matches=index.filter(r=>words.every(w=>(r.title+' '+r.chapter+' '+r.text).toLowerCase().includes(w)));const h=document.createElement('h2');h.textContent='搜索结果 · '+matches.length;results.append(h);for(const r of matches.slice(0,40)){const a=document.createElement('a');a.href='#'+r.id;a.className='result';const title=document.createElement('strong');title.textContent=r.chapter+' / '+r.title;const snippet=document.createElement('small');const at=Math.max(0,r.text.toLowerCase().indexOf(words[0])-35);snippet.textContent=r.text.slice(at,at+190);a.append(title,snippet);results.append(a)}if(!matches.length){const p=document.createElement('p');p.textContent='没有找到对应内容，可尝试“坐标”“暂停”“OpenVINO”等关键词。';results.append(p)}document.querySelector('#search-status').textContent='找到 '+matches.length+' 个章节';}
q.addEventListener('input',search);q.addEventListener('keydown',e=>{if(e.key==='Escape'){q.value='';search();q.blur()}if(e.key==='Enter'){results.scrollIntoView({behavior:'smooth'})}});
document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();q.focus()}});
document.querySelector('#print').addEventListener('click',()=>window.print());
document.querySelector('#expand').addEventListener('click',()=>document.querySelectorAll('.nav-group').forEach(d=>d.open=true));
document.querySelector('#collapse').addEventListener('click',()=>document.querySelectorAll('.nav-group').forEach(d=>d.open=false));
document.querySelectorAll('pre').forEach(pre=>{const b=document.createElement('button');b.className='copy';b.type='button';b.textContent='复制代码';b.addEventListener('click',async()=>{const value=pre.querySelector('code').textContent;try{await navigator.clipboard.writeText(value);b.textContent='已复制'}catch{const ta=document.createElement('textarea');ta.value=value;document.body.append(ta);ta.select();const ok=document.execCommand('copy');ta.remove();b.textContent=ok?'已复制':'请手动选择复制'}setTimeout(()=>b.textContent='复制代码',1600)});pre.after(b)});
function locate(){const id=decodeURIComponent(location.hash.slice(1));document.querySelectorAll('nav a').forEach(a=>{const active=a.getAttribute('href')==='#'+id;a.classList.toggle('active',active);if(active){const d=a.closest('details');if(d)d.open=true}})}window.addEventListener('hashchange',locate);locate();
'''
nav_html=''.join(nav)
home='''<header class="hero" id="home"><div class="eyebrow">FACTORY DEMO / DOCUMENTATION</div><h1>通用视觉工作台 · 阅读手册</h1><p class="lead">从一张图片开始，理解输入、模型、数据库与浏览器之间的数据如何流动。产品说明、代码约定和性能分析集中在这一页。</p><span class="badge">本机离线阅读</span><span class="badge">5 张数据流图</span><span class="badge">2026-10-28 · V1.3</span><div class="route"><strong>建议阅读顺序</strong><p><a href="#start">① 开始使用</a><a href="#flow">② 数据流图解</a><a href="#product">③ 产品边界</a><a href="#architecture">④ 架构与代码</a><a href="#analysis">⑤ 性能分析</a></p></div><div class="toolbar"><button id="print">打印 / 保存 PDF</button><button id="expand">展开全部目录</button><button id="collapse">收起目录</button><a class="tool-link" href="../DATA_FLOW_GUIDE.md">数据流原稿</a><a class="tool-link" href="diagrams/flow-map.json">图结构数据</a></div><p class="note">正文、图示与验收截图已嵌入页面，不需要启动后端。历史50张模型实测与本轮协议/界面验证分别记录；生产吞吐与硬件联动尚未验证。源代码、原始证据和外部文献链接需保留项目目录或联网才能打开。</p></header>'''
search_json = json.dumps(search, ensure_ascii=False).replace(chr(60), chr(92) + 'u003c')
page=f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Factory Demo · 完整阅读手册与数据流图解</title><style>{css}</style></head><body><aside class="sidebar"><div class="brand">FACTORY DEMO</div><p>产品 · 使用 · 代码 · 数据流</p><label for="query">搜索手册</label><input id="query" class="searchbox" type="search" placeholder="例如：数据流、暂停、坐标"><p class="search-help">Ctrl+K 搜索 · 多词以空格分隔</p><div id="search-status" class="sr-status" role="status" aria-live="polite"></div><a class="top-link" href="#home">阅读首页</a><nav aria-label="章节目录">{nav_html}</nav></aside><main>{home}<section id="results" class="results" aria-label="搜索结果" hidden></section>{"".join(sections)}<footer>生成源：当前项目文档与历史验收材料。图示依据实际代码核对，样式经用户选择。生成脚本：docs/web_manual/build_manual.py。<br>原稿中的“完整处理耗时”在推理章节网页版澄清为“四阶段处理合计”；未改写历史实测数据。</footer></main><a class="backtop" href="#home">回到目录</a><script id="search-index" type="application/json">{search_json}</script><script>{script}</script></body></html>'
(OUT/'index.html').write_text(page,encoding='utf-8')
def guide_link(m):
    target=html.unescape(m[2])
    if target.startswith(('#','data:')) or urlsplit(target).scheme:
        return m[0]
    parsed=urlsplit(target)
    dest=(OUT/unquote(parsed.path)).resolve()
    return f'{m[1]}="{esc(Path(os.path.relpath(dest,DOC)).as_posix())}{("#"+esc(parsed.fragment)) if parsed.fragment else ""}"'
(DOC/'GUIDE.html').write_text(re.sub(r'(href|src)="([^"]+)"',guide_link,page),encoding='utf-8')
(OUT/'source-manifest.json').write_text(json.dumps({'date':'2026-10-28','documents':manifest,'diagram_count':len(FIGURES),'self_contained_content':True,'note':'External evidence/source links are project-relative; text, diagrams and screenshot are embedded.'},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'html':str(OUT/'index.html'),'bytes':len(page.encode()),'chapters':len(DOCS),'search_entries':len(search),'diagrams':len(FIGURES)},ensure_ascii=False))


