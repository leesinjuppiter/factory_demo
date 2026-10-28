# Factory Demo 从零实现教学项目

直接双击 `index.html`。这是独立课程项目，不是原工作台的运行入口。20 节课包含实现步骤、代码说明、完整文件、预期现象、故障定位、练习与自测；课程网页和图示不依赖网络、数据库或运行中的后端。

## 目录

| 目录 | 用途 |
|---|---|
| index.html | 单文件课程网页，代码和图已嵌入 |
| lessons | 可维护教学正文与逐课 Markdown |
| examples | 协议、SVG、最小 API、教学适配器和 Runner 实验 |
| reference | 完整应用参考源码；采用教学端口和数据库约束 |
| practice | 留给你手写和运行的练习区；不会覆盖原项目 |
| tools | 环境探测、参考文件放置、权重导入、例子检查、网页生成 |
| diagrams | 5 张可独立打开的原项目数据流图，代表应用结构 |
| evidence | 原始来源、课程内容哈希与本次验证记录 |

## 开始学习

```powershell
$course = 'C:\Users\13480\Desktop\codex_\tmp\deliverables\factory_demo_tutorial'
$py = 'C:\Users\13480\miniconda3\envs\yolo_v5_obb\python.exe'
Set-Location $course
& $py -B tools\env_probe.py
```

从第00课开始。每节先按实现顺序手写文件，再展开完整参考代码对照；可选 `tools/course.py apply N` 会把截至第 N 节的参考文件放入 `practice/factory_demo`，只新增或跳过相同文件，保留不同的现有文件，不自动覆盖你的作业。它不安装依赖、不连接数据库、不加载模型。

## V1.3 通用展示与持续落盘来源

当前参考代码新增展示契约、只读WS、独立预览、纯画布、inbox与模拟拍照。第02/06/08/09/13/14节已重写，reference同步但practice不变。课程仍用8876/5176与factory_demo_test_tutorial。来源哈希见[evidence/revision-v1.3.json](evidence/revision-v1.3.json)；本轮检查结果另行记录。下面V1.2记录保留为历史证据。

## V1.2 工业展示与管理分离（历史）

本轮实际验证见 [V1.2 验证记录](evidence/industrial-display-validation.json)：包含展示页坐标与异常状态、11章手册、20课/37份源码的浏览器检查，以及教学参考文件同步哈希。未创建教学数据库或运行新的真实推理。

练习首页 `/` 为深蓝工业展示与坐标；`/admin.html` 保持浅色，负责配置、任务控制和历史。第13课讲逆CTM、框选择与已加载帧事件，第14课提供 DisplayApp/AdminApp 双入口和 display.css 完整源码，第19课加入同帧与只读验收。本教程仍采用浅色阅读风格；reference 更新不覆盖 practice。

## 与原项目的隔离

- 练习 API 为 `127.0.0.1:8876`，最小 API 实验为 `8877`，Vue 开发服务为 `5176`。
- 练习 Store 只接受 `factory_demo_test_tutorial` 数据库；角色为 `factory_demo_tutorial`。必须由你在第07课主动运行初始化，制作课程时没有建立数据库。
- 不复制原项目 `.env`、管理员凭据、运行快照、历史、node_modules 或数据库内容。
- 已带入必要 vendor 源码、许可证及当前 Windows/Python 环境的 NMS 扩展；未复制大模型权重或数据集。第12课工具从你本机的可信权重副本按 SHA-256 校验后导入练习区。
- 数据源配置针对本机现有数据集。搬迁课程需修改路径并准备兼容模型环境。vendor 中保留的原始清单用于来源追踪，不表示课程已包含清单所述大权重。
- 完成第14课前练习前端尚未完整；中间阶段以例子和 API 文档验收，不能提前把首页缺失当作模型故障。

## 初版课程验证范围与 V1.2 更新

以下 Runner 和教学替身等测试属于初版课程验证。V1.2 更新正文、图示与参考前端；对应来源哈希见 `evidence/revision-v1.2.json`，本轮浏览器验证另行记录，不重写原始验证数据。

本次验证教学网页、完整源码语法、最小 API 请求校验、协议合法/非法输入、真实 Runner 配教学替身与内存存储的三图流程，以及参考文件工具不覆盖手写修改的行为。

没有为课程新建 PostgreSQL、安装 npm 依赖、构建练习前端、导入大权重、运行真实推理或完整50张测试。这些步骤由你按课程逐节完成；原项目已有验收结果不是练习项目的新实测成绩。

## 更新课程

修改 `lessons/content.py`、相关例子或参考源码后运行：

```powershell
& $py -B tools\build_course.py
```

网页的学习进度是手动标记，保存在当前浏览器 localStorage；可导出 JSON 留存。更换浏览器、移动路径或清理存储可能使进度不同。搜索支持多个空格分隔关键词。打印遵循当前浏览器能力，代码折叠状态会影响打印内容；本次没有输出教学 PDF。

V1.3 教学运行依赖包含 `websockets==15.0.1`，用于 uvicorn 的 WebSocket 支持。先检查 reference/requirements-api.txt 与 yolo_v5_obb 环境；HTTP 成功不代表 WS 已可连接。

项目V1.3真实/模拟展示的集成证据已另附 evidence/v13-browser-validation.json、v13-live-flow.json 与 v13-real-desktop.png / v13-mock-desktop.png / v13-history.png。这些是项目运行证据；教学练习尚未自动创建或运行，不代表你的practice已经验收。

## 云端 GPU 补充

参考适配器现在支持显式CPU/CUDA FP32，默认CPU。本轮RTX3080Ti部署经过真实验证，见[CLOUD_DEPLOYMENT.md](CLOUD_DEPLOYMENT.md)及[evidence/cloud-validation-20261028.json](evidence/cloud-validation-20261028.json)。课程仍采用独立教学数据库/端口，不因参考代码同步而修改practice。云端正式项目使用8765/factory_demo，教学练习仍使用8876/factory_demo_test_tutorial；不要直接用正式.env启动练习。GPU测试需要已编译扩展及匹配的数据路径。
