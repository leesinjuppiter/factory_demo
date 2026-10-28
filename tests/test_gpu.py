"""CUDA NMS and real-model parity; skipped when CUDA is unavailable."""
from pathlib import Path
import sys

import numpy as np
import pytest
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "vendor/yolov5_obb"))
pytestmark = pytest.mark.skipif(not torch.cuda.is_available(), reason="requires a CUDA device and built extension")


def test_cuda_nms_matches_cpu_across_blocks_and_filtered_indices():
    from utils.nms_rotated import obb_nms
    generator = torch.Generator().manual_seed(42)
    boxes = torch.cat((torch.rand((256, 2), generator=generator) * 200,
                       torch.rand((256, 2), generator=generator) * 30 + 5,
                       torch.rand((256, 1), generator=generator) * 3.14), dim=1)
    boxes[10] = boxes[11]
    boxes[3, 2] = 0  # removal must preserve the original CUDA indices
    scores = torch.linspace(.99, .1, len(boxes))
    _, expected = obb_nms(boxes, scores, .45)
    stream = torch.cuda.Stream()
    with torch.cuda.stream(stream):
        _, actual = obb_nms(boxes.cuda(), scores.cuda(), .45)
    stream.synchronize()
    assert actual.device.type == "cuda"
    assert actual.cpu().tolist() == expected.tolist()


@pytest.mark.parametrize("tiny", [False, True])
def test_cuda_nms_empty_and_all_filtered(tiny):
    from utils.nms_rotated import obb_nms
    boxes = torch.zeros((3 if tiny else 0, 5), device="cuda")
    result, keep = obb_nms(boxes, torch.zeros(len(boxes), device="cuda"), .45)
    assert len(result) == len(keep) == 0
    assert keep.device.type == "cuda"


def test_real_cpu_cuda_fp32_prediction_parity():
    import cv2
    from backend.inference.pytorch_obb import PytorchOBBAdapter
    paths = sorted((ROOT.parent / "dataset/dataset4911_obb_smoke_50/test/images").glob("*.jpg"))
    assert paths, "cloud smoke dataset is required for CUDA acceptance"
    image = cv2.imread(str(paths[0]))
    cpu = PytorchOBBAdapter(ROOT / "vendor/weights/factory_now.pt", device="cpu")
    gpu = PytorchOBBAdapter(ROOT / "vendor/weights/factory_now.pt", device="cuda:0")
    cpu.load()
    assert gpu.load()["device"] == "cuda:0"
    parameters = dict(image_size=640, confidence=.25, iou=.45, max_det=300)
    expected = cpu.predict(image, **parameters)["detections"]
    result = gpu.predict(image, **parameters)
    remaining = result["detections"].copy()
    assert len(expected) == len(remaining)
    for detection in expected:
        candidates = [d for d in remaining if d["class_id"] == detection["class_id"]]
        assert candidates
        match = min(candidates, key=lambda d: np.abs(np.array(d["polygon"]) - detection["polygon"]).max())
        np.testing.assert_allclose(match["polygon"], detection["polygon"], atol=1., rtol=.001)
        assert abs(match["confidence"] - detection["confidence"]) < .002
        remaining.remove(match)
    assert all(np.isfinite(t) and t >= 0 for t in result["timing_ms"].values())
