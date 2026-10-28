# Git 管理与环境恢复

仓库：https://github.com/leesinjuppiter/factory_demo.git；主分支：`main`。

## 管理范围与约束

保存应用源码、必要的 YOLOv5-OBB vendor 源码与许可证、当前 Windows CPython 3.10 的 NMS 扩展、配置模板、文档源文件、生成的离线网页、测试及验收证据。`tutorial/` 是独立教学项目的交付副本，包含20课、示例与参考源码，可单独复制出去学习。

不保存 `.env`、权重、数据集、运行快照、数据库、node_modules、dist 或个人练习。原独立教程位于 `C:\Users\13480\Desktop\codex_\tmp\deliverables\factory_demo_tutorial`，同步教程时不覆盖其中的 practice。两处教程不是自动双向同步目录；后续修改后须重新生成、核对再提交。

约束：Git 只能恢复已提交内容；仓库不是生产数据备份。vendor 清单记录本机来源，不能理解为远端仓库含权重。保留上游 GPL-3.0 许可和文件头；二进制扩展不保证换环境后可直接使用。

## 克隆到另一台机器

```powershell
git clone https://github.com/leesinjuppiter/factory_demo.git
Set-Location factory_demo
```

1. 按 README 准备兼容的 Python/PyTorch 环境；本轮实际验证环境为本机 Conda `yolo_v5_obb`。`requirements-api.txt` 仅列 API 侧依赖，不是完整 GPU 环境锁文件。
2. 从可信本地备份放回 `vendor/weights/factory_now.pt`，SHA-256 应为 `62af01dbc971d332ad4813d5f2811243f555877ffbdb0755fe428159687ef037`。不从不明来源加载 PyTorch checkpoint。
3. 准备图片数据，调整 `configs/local.json` 数据源路径；建立 `runtime/camera_inbox` 接收目录。数据和路径不由 Git 自动恢复。
4. 按 README 的数据库初始化说明配置独立 PostgreSQL 和本地 `.env`，不要复用教程数据库。`.env.example` 仅为模板。
5. 在 `frontend` 执行 `npm ci` 和 `npm run build`，回到项目根目录运行环境检查与 `start.py`。更换操作系统/Python/PyTorch 后按 vendor 说明重新编译 NMS 扩展并验证。
6. 只检查展示协议时，可在构建前端后执行 `python -B scripts/mock_display.py --port 8879`，访问 `http://127.0.0.1:8879/`；这一路不需要数据库或模型，不表示真实推理已可用。

约束：当前配置、课程命令和历史证据保留本机绝对路径。迁移时须修改路径；旧验收记录不能证明新机器部署成功。离线 HTML 需下载后用浏览器打开，GitHub 文件页不等于网站托管。

## 日常提交

```powershell
git status --short
git diff
git add <本次修改的文件>
git diff --cached --stat
git commit -m "说明具体变化"
git push origin main
```

约束：提交前核对暂存区，不添加凭据、模型或运行数据；多人修改时先拉取并解决冲突，不强制推送覆盖历史。当前版本验证详情见 `evidence/v13-validation.json`，性能验证边界仍见 V1.3 文档。
