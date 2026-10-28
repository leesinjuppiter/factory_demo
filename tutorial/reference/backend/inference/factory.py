"""Small explicit engine registry; unavailable engines are never silently replaced."""
from typing import Protocol


class InferenceAdapter(Protocol):
    def load(self) -> dict: ...
    def predict(self, image, **parameters) -> dict: ...


def capabilities(weights):
    return [
        {"id": "pytorch", "label": "PyTorch · YOLOv5-OBB", "available": weights.is_file(),
         "reason": None if weights.is_file() else "配置的权重不存在"},
        {"id": "openvino", "label": "OpenVINO · Intel CPU", "available": False,
         "reason": "本版未实现；需要专用 OBB 导出与适配验证"},
        {"id": "tensorrt", "label": "TensorRT · NVIDIA GPU", "available": False,
         "reason": "本版未实现；需要 GPU 环境与匹配的 engine"},
    ]


def create_adapter(engine, weights):
    if engine != "pytorch":
        raise ValueError("此引擎尚未实现或验证")
    from .pytorch_obb import PytorchOBBAdapter
    return PytorchOBBAdapter(weights)
