# Factory Demo · 通用工业视觉工作台

仓库：<https://github.com/leesinjuppiter/factory_demo>，主分支 `main`。源码、网页版手册、验证记录和独立教程副本纳入 Git；模型权重、数据集、`.env`、运行图片、数据库及练习成果不上传。克隆后的恢复步骤见 [Git 与环境恢复说明](docs/GIT_WORKFLOW.md)。[仓库内教学网页](tutorial/index.html) 可下载后离线打开；原独立教学目录仍保留。

本项目把单图/图片目录、YOLOv5-OBB 真实推理、检测画面、运行控制、PostgreSQL 历史和结果导出连成一个本机流程。前端通过统一协议显示 HBB/OBB 四点框，不绑定特定类别或推理引擎。

**本版实际实现 PyTorch YOLOv5-OBB CPU。OpenVINO、TensorRT 显示为未实现；无 CVAT、标注、训练、视频或真实相机 SDK 接入。**

默认权重为用户指定 `factory_now.pt` 的独立副本。实际权重 **8 类**，而 smoke 数据集 **7 类且顺序不同**；本版显示与统计采用权重顺序，不计算精度。请先阅读下方类别说明。


## V1.3 当前实施说明

本版新增通用展示协议、只读 WS 结果推送、独立预览工作线程、受控不可变图片 URL、纯画布及实时/历史适配。生产来源方向已确定为“相机先落盘，再由程序读取”，通过持续 inbox 和模拟拍照脚本验证接口；不默认改为 SDK 内存主路线。

- [V1.3 使用与边界](docs/V1_3_DECOUPLING.md)
- [模拟拍照与持续目录](docs/CAMERA_INBOX.md)
- [当前协议](docs/CONTRACT.md) / [架构](docs/ARCHITECTURE.md) / [文档状态索引](docs/DOCUMENT_STATUS.md)
- [离线网页版手册](docs/GUIDE.html)

展示可连接独立协议模拟后端，模拟数据不能当作真实检测性能。PostgreSQL 仍是任务持久化依赖；内存状态可读不等于已经实现数据库离线持续生产。默认仅本机，OV/TRT仍不可用。

## 展示与后台入口（V1.3）

- 展示页：`http://127.0.0.1:8765/`，深蓝工业大屏，只读取结果，支持原图指针和检测框四点坐标。
- 后台管理：`http://127.0.0.1:8765/admin.html`，负责任务参数、控制、历史与导出。
- 详细边界见 [模块分离说明](docs/MODULE_SPLIT.md) 与 [工业展示说明](docs/INDUSTRIAL_DISPLAY.md)。
- 坐标标签默认关闭；点击检测框查看四点，展开坐标明细可检查全部可见目标。后台和阅读文档保持浅色风格。

## 1. 直接启动

项目位置：`C:\Users\13480\Desktop\codex_\factory_demo`。

后端固定使用 `C:\Users\13480\miniconda3\envs\yolo_v5_obb\python.exe`，本地 PostgreSQL 服务需运行。配置与独立数据库已由实施流程建立时，不必重复初始化。

**PowerShell**

```powershell
Set-Location 'C:\Users\13480\Desktop\codex_\factory_demo'
& 'C:\Users\13480\miniconda3\envs\yolo_v5_obb\python.exe' -B scripts\check_env.py
& 'C:\Users\13480\miniconda3\envs\yolo_v5_obb\python.exe' -B start.py
```

**CMD / Anaconda Prompt**

```bat
cd /d C:\Users\13480\Desktop\codex_\factory_demo
start.cmd
```

启动后打开 [本机工作台](http://127.0.0.1:8765)。接口文档在 [本机 API 文档](http://127.0.0.1:8765/docs)，健康检查在 [health](http://127.0.0.1:8765/api/health)。

服务使用单进程、单 worker；不要同时开两个 `start.py`，也不要增加 Uvicorn worker。数据库锁会拒绝同库第二个实例。终端 Ctrl+C 退出；正在执行的模型调用会先等待帧边界，普通关闭最多等待 30 秒，异常退出的未完成任务在下次启动标为 interrupted。

## 2. 第一次操作

1. 打开后台管理 `http://127.0.0.1:8765/admin.html`，选择 `Smoke 50 · 测试集（10 张）`，或上传一张 JPG/JPEG/PNG/BMP。
2. 保留默认 PyTorch、输入尺寸 640、置信度 0.25、NMS IoU 0.45、最多 300 框、目标回放 1 FPS。
3. 点击开始。首次运行需要加载约 8,743 万参数的权重并预热，页面显示 loading；这段等待不是卡死，也不计入每图推理均值。
4. 在展示页 `http://127.0.0.1:8765/` 查看原图、旋转框、类别、置信度和统计。可以隐藏框/标签、按类别筛选、缩放或全屏。
5. 暂停会在当前帧结束后生效；继续处理剩余图片。停止保存已经完成的部分，不强行打断 PyTorch 原生算子。
6. 一次遍历结束后进入 completed。到后台“历史记录”查看配置与逐图结果，下载 JSON/CSV 或单图绘框 PNG。

浏览器关闭不会停止后台任务；刷新和切页不创建新任务。多个本机浏览器共享同一活动任务和控制权。

上传源候选列表保存在当前页面内存中，刷新后不会自动重新列出以前上传的文件；已经创建的任务和图片历史仍然保留。需要再次作为新输入时重新选择上传文件。

## 3. 重要语义

| 信息 | 正确解释 |
|---|---|
| 当前图片目标数 | 当前帧模型输出的检测框数量 |
| 累计目标数 | 本次运行各图片检测实例数之和，不是跨帧去重实物数 |
| 置信度 | 模型预测分数，不是准确率 |
| 无检测 | 该帧成功处理但未保留检测框，不等于读取/推理失败 |
| completed | 遍历结束，仍需看失败图片数，不保证每张成功 |
| 处理 FPS | `1000 / 成功图片处理均值ms`，不是浏览器显示或端到端吞吐 |
| 目标回放 FPS | 调度目标，算力不足时按实际速度，不补发落后时隙 |
| 重新运行 | 创建新运行 ID，保留之前的历史 |

原图四点坐标在原始像素坐标系中。前端只按比例缩放，不把像素坐标当归一化标签。

## 4. 权重与类别映射

权重副本：`vendor/weights/factory_now.pt`。

SHA-256：`62af01dbc971d332ad4813d5f2811243f555877ffbdb0755fe428159687ef037`。

| 权重 ID | 名称 | smoke 数据集 ID |
|---:|---|---:|
| 0 | coal | 0 |
| 1 | rockbolt | 1 |
| 2 | mesh | 2 |
| 3 | bottle | 6 |
| 4 | stick | 3 |
| 5 | board | 4 |
| 6 | cap | 5 |
| 7 | plate | 无对应类 |

界面、数据库和预测导出全部遵循权重 ID。完整数据集评估前需按名称映射，并单独确定 `plate` 的评估规则。不得直接把预测 ID 与标签 ID 逐项比较。

## 5. 配置其他图片目录

配置位于 [configs/local.json](configs/local.json)。网页只选择已经登记的源，不接收任意服务器路径。增加源后重启服务，例如在 `sources` 数组加入：

```json
{
  "id": "my_images",
  "label": "我的测试图片",
  "path": "D:/vision_data/images"
}
```

路径可为绝对路径，或相对于项目根目录的路径。源 ID 必须唯一。目录只扫描第一层；不递归处理子目录。创建任务时冻结清单并记录文件大小/修改时间，之后新增图片留到下一次任务。

默认数据源引用旁边 YOLOv5-OBB 项目的 smoke 数据集。推理代码与权重已复制进新项目，不依赖旁边仓库代码运行；图片数据仍是外部可配置资源。搬迁项目后需要修改这些路径。

**本版资源上限**

| 资源/参数 | 限制 |
|---|---|
| 图片文件 | ≤20 MiB，≤4,000 万像素 |
| 单任务 | ≤10,000 张 |
| 上传文件名 | ≤180 字符 |
| 输入尺寸 | 320～1280，32 的整数倍 |
| 置信度 | 0.001～1 |
| NMS IoU | 0.01～1 |
| 最大输出框 | 1～1000 |
| 目标回放 FPS | 0.1～10 |
| API 分页 | 每页 ≤100 |
| runtime 磁盘保护 | 开始/上传/逐帧前至少剩余 1 GiB |

磁盘检查不是整个任务的预留容量，也不能保护其他盘上的 PostgreSQL。没有自动删除历史和图片，长期运行需离线归档。

## 6. 本地数据与备份

| 位置 | 用途 |
|---|---|
| `.env` | 独立 PostgreSQL 连接凭据；被 Git 忽略 |
| `configs/local.json` | 模型、源目录、默认参数与 runtime 位置 |
| `runtime/uploads/<uuid>/` | 上传图片与源名称 |
| `runtime/runs/<run_id>/images/` | 本次实际输入的原始字节快照 |
| 工作区 `tmp/YYYYMMDD-factory-demo-runtime/<进程号>/` | 本机运行临时文件与库缓存 |
| PostgreSQL `factory_demo` | `factory_runs`、`factory_frames` 历史与检测结果 |
| 工作区 `tmp/20261028-factory-demo-01a180ab/` | 本次开发和验证证据，不是用户正式运行数据 |

删除原输入目录不会影响已经保存的图片快照；删除 runtime 快照会导致历史图片无法打开，数据库记录仍然存在。备份应同时保留数据库、runtime、配置和权重哈希。重复推理同一图片会产生新的快照与历史，占用额外空间。

不要用 `test_demo` 或 `test_demo_new` 的业务数据库替代本项目数据库。程序限制生产库名为 `factory_demo`，避免误写旧库。

## 7. 重建依赖与数据库

本节用于迁移或环境损坏后的恢复。本机已经配置好时无需重复执行。

API 新增依赖固定在 [requirements-api.txt](requirements-api.txt)。它**不包含完整模型环境**；已有 `yolo_v5_obb` 中的 Torch、torchvision、OpenCV、NumPy 等仍是运行前提。不要为了安装 API 依赖重装 Torch 或切换 CUDA。

```powershell
Set-Location 'C:\Users\13480\Desktop\codex_\factory_demo'
& 'C:\Users\13480\miniconda3\envs\yolo_v5_obb\python.exe' -m pip install -r requirements-api.txt
Set-Location frontend
npm ci
npm run build
Set-Location ..
```

前端生产文件位于 `frontend/dist`，由 API 托管；修改前端后重新 build，再重启服务。独立开发时可在 frontend 运行 `npm run dev`，Vite 将 `/api` 转发到本机 8765。

数据库初始化脚本为 `scripts/setup_db.py`，支持 `--from-env` 读取一个本机管理员 `.env` 中的连接，或使用进程环境变量 `FACTORY_ADMIN_DATABASE_URL`。它连接本机 PostgreSQL 的管理库，建立独立 `factory_demo` 非超级用户与同名数据库，并把随机生成的应用凭据写入新项目 `.env`；不会复制管理员密码到新配置。

示例命令中的路径需替换为已有的本机管理员配置文件：

```powershell
& 'C:\Users\13480\miniconda3\envs\yolo_v5_obb\python.exe' -B scripts\setup_db.py --from-env 'C:\path\to\local-admin.env'
```

已有 `.env` 时脚本只检查连接，不覆盖。没有 `.env` 但同名角色/数据库已存在时拒绝覆盖，需要手工配置正确连接。不要将密码粘贴到文档、聊天或命令输出中。

vendor 内含当前 Windows x64 / CPython 3.10 / PyTorch 环境编译的 CPU rotated-NMS 扩展。换操作系统、Python 或 Torch 版本后可能需要用保留源码重新编译；当前二进制不保证跨环境可用。详见 [vendor/README.md](vendor/README.md)。

## 8. 故障处理

| 现象 | 检查与处理 |
|---|---|
| 页面无法连接 | 确认 start.py 终端仍运行，访问 127.0.0.1:8765，检查端口是否已占用 |
| 数据库连接错误 | 确认 PostgreSQL 服务运行、`.env` 指向 factory_demo；恢复数据库后重启应用 |
| 拒绝第二个实例 | 关闭旧的 factory_demo 服务，不要同时使用多个 worker |
| 前端尚未构建 | 在 frontend 执行 npm ci、npm run build 后重启 |
| 模型加载失败 | 运行 check_env，核对权重路径/哈希与环境；不要用其他 YOLO 版本权重随意替换 |
| NMS 扩展导入失败 | 核对 CPython/Torch/操作系统，使用原目标环境或重新编译，不绕过 NMS |
| 源为空 | 目录须存在且第一层包含支持格式，默认路径相对项目根目录 |
| 运行中图片失败 | 历史查看逐帧原因，检查损坏图、变化文件、体积/像素上限 |
| 没有检测框 | 确认是合法空结果还是错误；检查阈值与图片，不能据此认定模型失效 |
| 停止后短暂等待 | 当前模型调用尚未返回，停止在帧边界执行 |
| 历史有记录但无图 | 检查 runtime 快照是否被移动/删除，数据库中仍有检测记录 |
| 剩余空间不足 | 停止任务后备份和离线归档；不要删除 PostgreSQL 数据目录 |

本版仅监听本机，没有账户登录和多用户授权。将监听地址改为公网并不能完成生产部署；局域网/公网版本需另行设计身份、权限、连接保护和资源配额。

## 9. 文档与代码入口

- [可直接打开的完整中文说明书](docs/GUIDE.html)：汇集产品、代码、接口和验收内容，无需联网。
- [本次验收报告](docs/VERIFICATION.md)：真实50张结果、测试、浏览器与重启证据、未验证边界。
- [产品需求与逐功能边界](docs/PRODUCT.md)：详细功能、资源、状态、异常和验收条件。
- [架构与代码说明](docs/ARCHITECTURE.md)：职责、调用链、坐标、存储与扩展方式。
- [公共 API 协议](docs/CONTRACT.md)：前后端统一字段和接口。
- [推理模块说明](docs/INFERENCE.md)：真实模型、类别映射、原 detect 对比与 NMS 边界。
- [性能验证与完整数据集指南](docs/PERFORMANCE.md)：计时口径、流程测试与后续精度评估。
- `backend/app.py`：API、上传、资源与导出入口。
- `backend/runner.py`：单任务生命周期、逐图工作与统计。
- `backend/store.py`：PostgreSQL 事务、查询、单实例锁和中断恢复。
- `backend/images.py`：目录清单、读图校验与空间检查。
- `backend/inference/pytorch_obb.py`：PyTorch OBB 适配器。
- `frontend/src/`：独立 DisplayApp 展示页、AdminApp 后台管理页与共享坐标画布。

验证结论以本次交付验收记录为准。单图与 50 张流程测试不能证明完整数据集精度、连续工业吞吐或 OpenVINO/TensorRT 已可用。

## 10. 自行复现小数据集流程

保持服务已经启动，再开一个 PowerShell 终端：

```powershell
Set-Location 'C:\Users\13480\Desktop\codex_\factory_demo'
& 'C:\Users\13480\miniconda3\envs\yolo_v5_obb\python.exe' -B scripts\smoke.py --output 'C:\Users\13480\Desktop\codex_\tmp\deliverables\factory_demo\smoke50-local.json'
```

默认分别执行测试 10 张、验证 10 张、训练 30 张；使用真实 HTTP、真实模型与 PostgreSQL，创建新的运行记录及图片快照，不修改原数据集。脚本把目标回放设为 10 FPS 以减少人为等待，实际参数和耗时保存在报告中；运行结束不计算精度。

只检查测试子集可以追加 `--sources smoke_test`。`--timeout` 控制每个任务的等待秒数，默认 600；超时时脚本报错，不自动删除记录或强制终止后台模型，应在后台任务管理查看并按需停止。

真实模型单元测试：

```powershell
& 'C:\Users\13480\miniconda3\envs\yolo_v5_obb\python.exe' -B tests\test_inference.py -v
```

API 边界测试使用真实 PostgreSQL 的独立临时 schema 和明确的推理替身，不能当作模型精度证明。执行时把 pytest 缓存与临时文件指定到工作区的独立测试目录；结束时测试仅清理自身 schema，不删除应用业务记录。


V1.3 实时展示需要 `websockets==15.0.1`（已列入 requirements-api.txt）。启动环境需支持真实 WS 升级；HTTP 健康接口成功不证明实时推送可用。独立协议模拟器为 `python -B scripts/mock_display.py --port 8879`，构建前端后访问 http://127.0.0.1:8879/。
