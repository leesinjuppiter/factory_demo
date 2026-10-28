# YOLOv5-OBB 运行依赖副本

本目录用于让 factory_demo 独立于旁边的原始仓库源码运行。不是新的模型算法实现。

- 来源：本机 `C:\Users\13480\Desktop\codex_\yolov5_obb-master` 的当前文件，2026-10-28 复制；未声称对应某一上游 Git 提交。
- 授权声明：复制的源代码保留原文件头，完整 GPL-3.0 许可位于 `yolov5_obb/LICENSE`。权重来源为用户指定的本地文件，未重新训练、转换或修改。
- 保留范围：checkpoint 反序列化需要的 `models`，它们直接依赖的 `utils`，以及 rotated-NMS C++/CUDA 源码、构建脚本和本机已编译的 CPU 扩展。
- 不包含：原数据集、训练/验证入口、历史实验、前端、原始配置、网络下载资产。
- `MANIFEST.json` 记录每个副本相对于本地来源的路径、原始和副本 SHA-256，用于区分复制与修改。`weights/factory_now.pt` 为只读使用的完整副本。

## 本地适配

仅调整以下运行副作用，不调整网络前向、letterbox、OBB NMS、旋转框转换或坐标还原公式：

1. `utils/plots.py`：导入时不创建全局用户目录、不下载字体；找不到本地字体时使用 Pillow 默认字体。应用自身不调用旧 Annotator 绘制前端框。
2. `utils/downloads.py`：`attempt_download` 只接受存在的本地文件，缺失立即报错，不联网。
3. `utils/general.py`：`check_requirements` 默认不自动安装依赖；实际适配器不调用 CLI 的安装检查入口。

副本包含部分被旧模块导入的训练/绘图辅助函数，未对它们做全面裁剪，以保持全模型 checkpoint 的兼容性。它们不是 factory_demo 对外功能。OpenVINO/TensorRT 不通过旧 DetectMultiBackend 的其他分支启用。

## 二进制扩展边界

`nms_rotated_ext.cp310-win_amd64.pyd` 是当前 Windows x64 / CPython 3.10 / 本机 PyTorch 环境的 CPU 扩展。它不是跨 Python、操作系统、PyTorch 版本可移植的二进制文件。更换环境后若导入失败，应在目标环境使用保留源码重新编译；不能把“源码存在”解释成新环境已验证。CUDA 源码存在不表示当前已编译或验证 CUDA NMS。

`poly_nms` 的 CPU 实现不可用；本版使用的是 `obb_nms`，已用重复旋转框验证实际抑制行为。
