"""Real CPU inference checks. Run with yolo_v5_obb; no downloads or training."""
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.inference.pytorch_obb import PytorchOBBAdapter


class InferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = PytorchOBBAdapter(ROOT / "vendor/weights/factory_now.pt")
        cls.metadata = cls.adapter.load()

    def test_checkpoint_class_order_is_preserved(self):
        self.assertEqual([c["name"] for c in self.metadata["classes"]],
                         ["coal", "rockbolt", "mesh", "bottle", "stick", "board", "cap", "plate"])
        self.assertEqual(self.metadata["device"], "cpu")
        self.assertEqual(len(self.metadata["sha256"]), 64)

    def test_load_returns_detached_metadata(self):
        other = self.adapter.load()
        other["classes"][0]["name"] = "modified"
        self.assertEqual(self.adapter.metadata["classes"][0]["name"], "coal")

    def test_empty_detection_is_a_successful_prediction(self):
        result = self.adapter.predict(np.zeros((96, 160, 3), dtype=np.uint8),
                                      image_size=320, confidence=1.0, iou=.45, max_det=50)
        self.assertEqual(result["detections"], [])
        self.assertTrue(all(np.isfinite(value) and value >= 0 for value in result["timing_ms"].values()))

    def test_invalid_geometry_and_parameters_fail_explicitly(self):
        for image, kwargs in [
            (np.zeros((0, 160, 3), dtype=np.uint8), {}),
            (np.zeros((96, 160, 3), dtype=np.float32), {}),
            (np.zeros((96, 160, 3), dtype=np.uint8), {"confidence": float("nan")}),
            (np.zeros((96, 160, 3), dtype=np.uint8), {"image_size": 333}),
            (np.zeros((96, 160, 3), dtype=np.uint8), {"max_det": 0}),
        ]:
            params = dict(image_size=320, confidence=.25, iou=.45, max_det=50)
            params.update(kwargs)
            with self.subTest(kwargs=kwargs, shape=image.shape, dtype=str(image.dtype)):
                with self.assertRaises(ValueError):
                    self.adapter.predict(image, **params)

    def test_rotated_nms_extension_suppresses_duplicate_box(self):
        import torch
        from utils.nms_rotated import obb_nms
        boxes = torch.tensor([[10., 10., 20., 4., .4], [10., 10., 20., 4., .4],
                              [100., 100., 20., 4., .4]])
        _, keep = obb_nms(boxes, torch.tensor([.9, .8, .7]), .45)
        self.assertEqual(keep.tolist(), [0, 2])


if __name__ == "__main__":
    unittest.main()
