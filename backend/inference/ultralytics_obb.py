"""Ultralytics YOLO26-OBB inference with original-image polygon output."""

from copy import deepcopy
import hashlib
import math
from pathlib import Path
from time import perf_counter

import numpy as np

from .. import profiling
from .pytorch_obb import COLORS


class UltralyticsOBBAdapter:
    def __init__(self, weights: Path, device="cpu"):
        self.weights = Path(weights).resolve()
        if device != "cpu" and not (device.startswith("cuda:") and device[5:].isdigit()):
            raise ValueError("device 必须为 cpu 或 cuda:N")
        self.device = device
        self.model = None
        self.metadata = None

    def load(self) -> dict:
        if self.model is not None:
            return deepcopy(self.metadata)
        if self.weights.suffix.lower() != ".pt" or not self.weights.is_file():
            raise ValueError(f"本版需要已存在的本地 .pt 权重：{self.weights}")

        import torch
        from ultralytics import YOLO

        device = torch.device(self.device)
        if device.type == "cuda" and device.index >= torch.cuda.device_count():
            raise RuntimeError(f"指定的推理设备不可用：{device}")
        if device.type == "cpu":
            torch.set_num_threads(min(4, torch.get_num_threads()))

        start = perf_counter()
        model = YOLO(str(self.weights))
        if model.task != "obb" or not model.names:
            raise ValueError("权重必须为包含类别的 Ultralytics OBB 模型")
        stride = int(model.model.stride.max().item())
        # The one-to-many head keeps the configured rotated NMS IoU effective.
        model.predict(np.zeros((320, 320, 3), dtype=np.uint8), imgsz=320,
                      device=self.device, end2end=False, verbose=False, save=False)
        load_ms = (perf_counter() - start) * 1000
        digest = hashlib.sha256()
        with self.weights.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        self.metadata = {
            "name": self.weights.stem,
            "path": str(self.weights),
            "sha256": digest.hexdigest(),
            "family": "yolo26-obb",
            "classes": [
                {"id": i, "name": name, "label": name, "color": COLORS[i % len(COLORS)]}
                for i, name in sorted(model.names.items())
            ],
            "box_type": "obb",
            "device": self.device,
            "device_name": torch.cuda.get_device_name(device) if device.type == "cuda" else "CPU",
            "precision": "float32",
            "cpu_threads": torch.get_num_threads(),
            "stride": stride,
            "load_warmup_ms": round(load_ms, 3),
        }
        self.model = model
        return deepcopy(self.metadata)

    def predict(self, image_bgr: np.ndarray, *, image_size: int,
                confidence: float, iou: float, max_det: int) -> dict:
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

        result, = self.model.predict(image_bgr, imgsz=image_size, conf=confidence, iou=iou,
                                     max_det=max_det, device=self.device, end2end=False,
                                     verbose=False, save=False)
        start = perf_counter()
        obb = result.obb.cpu()
        polygons = obb.xyxyxyxy.tolist()
        detections = []
        for index, (class_id, score, polygon) in enumerate(zip(obb.cls.tolist(), obb.conf.tolist(), polygons), 1):
            if (class_id not in result.names or not 0 <= score <= 1
                    or not all(math.isfinite(value) for point in polygon for value in point)):
                raise ValueError("检测输出含非法类别、置信度或坐标")
            detections.append({"id": index, "class_id": int(class_id), "class_name": result.names[class_id],
                               "confidence": score, "polygon": polygon})
        timing = dict(result.speed)
        timing["postprocess"] += (perf_counter() - start) * 1000
        profiling.record("adapter", preprocess_ms=timing["preprocess"], inference_ms=timing["inference"],
                         postprocess_ms=timing["postprocess"], detections=len(detections), device=self.device)
        return {"detections": detections, "timing_ms": timing}
