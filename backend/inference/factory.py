"""Small explicit engine registry; unavailable engines are never silently replaced."""
from typing import Protocol
import os

from ..contracts import engine_label


class InferenceAdapter(Protocol):
    def load(self) -> dict: ...
    def predict(self, image, **parameters) -> dict: ...


def capabilities(weights, model_family="yolov5-obb"):
    return [
        {"id": "pytorch", "label": engine_label("pytorch", model_family), "available": weights.is_file(),
         "reason": None if weights.is_file() else "配置的权重不存在"},
        {"id": "openvino", "label": "OpenVINO · Intel CPU", "available": False,
         "reason": "本版未实现；需要专用 OBB 导出与适配验证"},
        {"id": "tensorrt", "label": "TensorRT · NVIDIA GPU", "available": False,
         "reason": "本版未实现；需要 GPU 环境与匹配的 engine"},
    ]


def create_adapter(engine, weights, model_family="yolov5-obb"):
    if engine != "pytorch":
        raise ValueError("此引擎尚未实现或验证")
    device = os.getenv("FACTORY_DEVICE", "cpu")
    if model_family == "yolo26-obb":
        from .ultralytics_obb import UltralyticsOBBAdapter
        return UltralyticsOBBAdapter(weights, device=device)
    if model_family != "yolov5-obb":
        raise ValueError(f"不支持的模型系列：{model_family}")
    from .pytorch_obb import PytorchOBBAdapter
    return PytorchOBBAdapter(weights, device=device)
