# PyTorch YOLOv5-OBB 推理模块

## 已实现接口与运行方式

模块：`backend/inference/pytorch_obb.py`。`PytorchOBBAdapter(weights, device="cpu")` 接收可信的本地 `.pt` 权重路径和明确设备。`load()` 加载一次并返回模型元数据；`predict(image_bgr, image_size=..., confidence=..., iou=..., max_det=...)` 接收 OpenCV `uint8 H×W×3 BGR` 图像，返回标准检测列表和阶段耗时。

接口由单个后台推理线程顺序调用。不可在多个线程并发使用同一个适配器。支持CPU或CUDA FP32，默认CPU；应用通过FACTORY_DEVICE=cuda:N显式选择GPU，设备不可用则失败。CPU线程数为 `min(4, os.cpu_count())`。不存在自动设备或OpenVINO/TensorRT回退。云端配置和编译见[CLOUD_DEPLOYMENT.md](CLOUD_DEPLOYMENT.md)。

调用链按原仓库 `detect.py` 的 PyTorch 分支实现：

1. `DetectMultiBackend` 加载完整 checkpoint，融合卷积与 BatchNorm，设置 eval/FP32。
2. `letterbox(auto=True, stride=model.stride)` 保持比例缩放并填充；BGR→RGB，HWC→CHW，转连续数组，除以 255，增加 batch 维度。
3. 模型前向得到含类别概率与 180 个角度分类值的 CSL 输出。
4. `non_max_suppression_obb(..., multi_label=True)` 做类别感知旋转框 NMS。
5. `rbox2poly` 得到按边连续排列的四个顶点，`scale_polys` 去除填充并映射回原图。
6. 输出帧内检测序号、权重类别 ID/名称、置信度和原图像素坐标。

前端直接缩放这些四点坐标。它们不是现代 Ultralytics OBB 标签格式，也不是归一化坐标。四点可能出界，绘图视口裁切即可；逐点截断会改变旋转矩形形状，因此不在适配器中截断。

## 默认权重与数据集类别差异

默认权重副本：`vendor/weights/factory_now.pt`。

SHA-256：`62af01dbc971d332ad4813d5f2811243f555877ffbdb0755fe428159687ef037`。

实际加载得到 **8 类**：

| 权重 class_id | 名称 | smoke 数据集 class_id |
|---:|---|---:|
| 0 | coal | 0 |
| 1 | rockbolt | 1 |
| 2 | mesh | 2 |
| 3 | bottle | 6 |
| 4 | stick | 3 |
| 5 | board | 4 |
| 6 | cap | 5 |
| 7 | plate | 无对应类别 |

**展示、统计、存储和预测导出全部使用权重类别顺序。** 这与数据集的 7 类顺序不同，不能按整数索引直接比较预测与真值。本版不计算精度；未来计算完整数据集指标时，需先明确名称映射和额外 `plate` 类的处理规则，不能静默忽略预测或按错误索引计分。

真实加载模型汇总：444 个模块，87,431,737 个参数。不是轻量 smoke 随机权重，未为了演示替换用户指定权重。

## 边界与异常

- `load()` 不自动下载权重、字体或依赖。不存在的权重、非 `.pt` 文件、类别表与检测头不一致、非 CSL-180 输出均明确失败。
- checkpoint 使用 `torch.load(..., weights_only=False)`，只允许服务端配置的可信权重；图片上传接口不能上传/切换模型。
- 模型输入要求非空三通道 `uint8` 图像。文件格式、体积与像素数由输入层先验证。空检测列表是正常结果。
- 适配器验证阈值 0..1、最大框数 1..1000、输入尺寸 32..1280 且为 stride 的倍数；API 可以设置更严格的产品范围。
- `image_size` 为 letterbox 最大目标尺寸；`auto=True` 时实际输入短边按 stride 收缩，不保证每张都是正方形。当前 stride=32。
- 输出包含非法类别、非有限坐标、非有限前向结果或非法置信度时抛出错误，禁止将损坏输出标记为有效检测。
- 原 NMS 的候选上限为 30,000；`max_det` 仅限制最终输出数量，不代表前向候选数量或后处理耗时的严格上界。
- 暂停/停止由任务管理器在帧边界执行；无法中断正在进行的原生算子。用户界面需显示正在暂停/停止。
- 本版未启用随机增强、半精度、跨帧跟踪、多 worker 或多模型热切换。CUDA路径的阶段耗时在边界同步，包含数据传输，不等于完整链路延迟。
- 旧 checkpoint 需要顶层 `models.*`/`utils.*` 导入名称；如果当前进程已加载其他仓库的同名模块，适配器明确拒绝，要求独立启动。

## 计时口径

`load_warmup_ms` 包含模型加载/融合和一次 640×640 零图前向，不含 Python 首次依赖导入及后续 SHA-256 扫描。它是启动诊断值，不是全部启动时间。

每帧 `preprocess` 包含 letterbox、数组变换与张量构建；`inference` 是 CPU 模型前向墙钟时间；`postprocess` 包含结果有限性检查、NMS、四点坐标还原与协议序列化。不包含读图、数据库写入、HTTP 传输、浏览器绘制或人为回放间隔。任务层单独记录读图与完整处理耗时。

预热仅在加载时执行一次 640×640，改变输入尺寸或长宽比后的第一帧仍可能有额外开销。正式比较应明确各形状的预热方案，保留原始逐帧计时，并确保同一权重、尺寸、阈值、候选上限和线程数。

## 本次真实验证

环境：`C:\Users\13480\miniconda3\envs\yolo_v5_obb\python.exe`，PyTorch `2.14.1+cpu`，4 CPU 线程。

以 smoke test 子集的 `20250523_193046299_000174.jpg`（以实际文件后缀为准）验证，原图 1580×1080，输入 640，confidence=0.25，IoU=0.45，max_det=300：实际得到 45 个检测框。连续 3 次模型前向约 554 / 526 / 511 ms，后处理约 15 ms。这是单图诊断样本，不代表完整数据集吞吐或目标设备性能。

另外在独立进程调用**原仓库 `detect.run`**，相同权重、图片与参数输出 TXT，再与适配器逐项比较：45 个结果的类别和顺序一致，最大四点坐标差 0.004981 像素，最大置信度差 4.8841e-7，符合原 TXT `%g` 六位有效数字舍入。此检查验证非空旋转框链路一致性，不是准确率测试。

原始证据位于工作区 `tmp/20261028-factory-demo-01a180ab/inference/`：`smoke.json`、`parity.json`、`reference_detect.py` 和 `original_detect/`。全应用测试与 50 张流程结果见主验收报告。

测试命令（在 factory_demo 项目目录）：

```powershell
& C:\Users\13480\miniconda3\envs\yolo_v5_obb\python.exe -B tests\test_inference.py -v
```

测试覆盖真实权重类别顺序、元数据隔离、合法空检测、非法图片/参数以及 CPU rotated-NMS 对重合旋转框的真实抑制。
