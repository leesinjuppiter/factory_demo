"""Local CPU YOLOv5-OBB inference, following the source repository's detect.py.

The checkpoint is a trusted local PyTorch full-model checkpoint, not a user upload.
Call load/predict from the application's single inference worker, never concurrently.
"""

from copy import deepcopy
import hashlib
import math
import os
from pathlib import Path
import sys
from time import perf_counter

import numpy as np


VENDOR = Path(__file__).resolve().parents[2] / "vendor" / "yolov5_obb"
# Stable colors are metadata; the UI must not assume a particular class count.
COLORS = ("#087f8c", "#c46a20", "#7561b3", "#397a35", "#bb4d63", "#315fb1", "#8b6c36")


class PytorchOBBAdapter:
    def __init__(self, weights: Path):
        self.weights = Path(weights).resolve()
        self.model = None
        self.metadata = None

    def load(self) -> dict:
        """Load once on CPU and warm up; neither step contributes to per-frame timing."""
        if self.model is not None:
            return deepcopy(self.metadata)
        if self.weights.suffix.lower() != ".pt" or not self.weights.is_file():
            raise ValueError(f"本版需要已存在的本地 .pt 权重：{self.weights}")
        # Historical checkpoints pickle `models.*` and `utils.*`; keep those names
        # but refuse to silently reuse a different YOLO repository in this process.
        for name in ("models", "utils"):
            module = sys.modules.get(name)
            if module is not None and getattr(module, "__file__", None):
                if not Path(module.__file__).resolve().is_relative_to(VENDOR):
                    raise RuntimeError(f"发现其他仓库的 {name} 模块，请在独立进程启动 factory_demo")
        if str(VENDOR) not in sys.path:
            sys.path.insert(0, str(VENDOR))

        import torch
        from models.common import DetectMultiBackend
        from utils.augmentations import letterbox
        from utils.general import non_max_suppression_obb, scale_polys
        from utils.rboxs_utils import rbox2poly

        self.torch = torch
        self.letterbox = letterbox
        self.nms = non_max_suppression_obb
        self.scale_polys = scale_polys
        self.rbox2poly = rbox2poly
        threads = min(4, os.cpu_count() or 1)
        torch.set_num_threads(threads)
        start = perf_counter()
        model = DetectMultiBackend(str(self.weights), device=torch.device("cpu"))
        model.model.float().eval()
        raw_names = model.names
        names = [str(raw_names[i]) for i in range(len(raw_names))]
        if not names or len(names) != int(model.model.model[-1].nc):
            raise ValueError("权重类别表与检测头类别数量不一致")
        # Fail on HBB weights rather than interpreting ordinary output as CSL angles.
        with torch.inference_mode():
            probe = model(torch.zeros((1, 3, 640, 640), dtype=torch.float32))
        if probe.ndim != 3 or probe.shape[-1] != 5 + len(names) + 180:
            raise ValueError("模型输出不符合 YOLOv5-OBB CSL-180 协议")
        load_ms = (perf_counter() - start) * 1000
        digest = hashlib.sha256()
        with self.weights.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        self.metadata = {
            "name": self.weights.stem,
            "path": str(self.weights),
            "sha256": digest.hexdigest(),
            "classes": [
                {"id": i, "name": name, "label": name, "color": COLORS[i % len(COLORS)]}
                for i, name in enumerate(names)
            ],
            "box_type": "obb",
            "device": "cpu",
            "precision": "float32",
            "cpu_threads": threads,
            "stride": int(model.stride),
            "load_warmup_ms": round(load_ms, 3),
        }
        self.model = model
        return deepcopy(self.metadata)

    def predict(self, image_bgr: np.ndarray, *, image_size: int,
                confidence: float, iou: float, max_det: int) -> dict:
        """Return ordered four-corner polygons in original-image pixels.

        Class-aware multi-label NMS, BGR->RGB and auto-stride letterbox match
        detect.py's PyTorch branch. Coordinates intentionally are not clipped.
        """
        if self.model is None:
            raise RuntimeError("请先调用 load() 加载模型")
        if (not isinstance(image_bgr, np.ndarray) or image_bgr.dtype != np.uint8
                or image_bgr.ndim != 3 or image_bgr.shape[2] != 3
                or min(image_bgr.shape[:2]) <= 0):
            raise ValueError("输入必须是非空 uint8 H×W×3 BGR 图片")
        if not 0 <= confidence <= 1 or not 0 <= iou <= 1:
            raise ValueError("confidence 和 iou 必须在 0 到 1 之间")
        if not isinstance(image_size, int) or not 32 <= image_size <= 1280 or image_size % self.metadata["stride"]:
            raise ValueError("image_size 必须在 32..1280 且是模型 stride 的整数倍")
        if not isinstance(max_det, int) or not 1 <= max_det <= 1000:
            raise ValueError("max_det 必须在 1..1000 之间")

        torch = self.torch
        with torch.inference_mode():
            t0 = perf_counter()
            im = self.letterbox(image_bgr, (image_size, image_size),
                                stride=self.metadata["stride"], auto=True)[0]
            im = np.ascontiguousarray(im.transpose((2, 0, 1))[::-1])
            tensor = torch.from_numpy(im).float().div_(255).unsqueeze(0)
            t1 = perf_counter()
            prediction = self.model(tensor, augment=False, visualize=False)
            t2 = perf_counter()
            if not torch.isfinite(prediction).all():
                raise ValueError("模型产生非有限数值，当前图片不记录为成功结果")
            det = self.nms(prediction, confidence, iou, multi_label=True, max_det=max_det)[0]
            polygons = self.rbox2poly(det[:, :5])
            if len(det):
                polygons = self.scale_polys(tensor.shape[2:], polygons, image_bgr.shape)
            detections = []
            for index, (row, polygon) in enumerate(zip(det.tolist(), polygons.tolist())):
                class_id, score = int(row[-1]), float(row[-2])
                if (not 0 <= class_id < len(self.metadata["classes"])
                        or not 0 <= score <= 1 or not all(math.isfinite(x) for x in polygon)):
                    raise ValueError("检测输出含非法类别、置信度或坐标")
                detections.append({
                    "id": index + 1,
                    "class_id": class_id,
                    "class_name": self.metadata["classes"][class_id]["name"],
                    "confidence": score,
                    "polygon": [[polygon[i], polygon[i + 1]] for i in range(0, 8, 2)],
                })
            t3 = perf_counter()
        return {
            "detections": detections,
            "timing_ms": {"preprocess": (t1 - t0) * 1000,
                          "inference": (t2 - t1) * 1000,
                          "postprocess": (t3 - t2) * 1000},
        }
