"""仅由本机配置指定可访问目录；HTTP 请求不能指定任意文件路径。"""
import json
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
LIMITS = {"max_file_bytes": 20 * 1024 * 1024, "max_pixels": 40_000_000,
          "max_images": 10000, "min_free_bytes": 1024 ** 3,
          "image_size_min": 320, "image_size_max": 1280, "image_size_step": 32,
          "confidence_min": 0.001, "confidence_max": 1, "iou_min": 0.01, "iou_max": 1,
          "max_det_min": 1, "max_det_max": 1000, "replay_fps_min": 0.1,
          "replay_fps_max": 10, "page_size_max": 100}
EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp"}
TERMINAL = {"completed", "stopped", "failed", "interrupted"}


class Settings:
    def __init__(self, config_path=None, database_url=None):
        load_dotenv(ROOT / ".env", override=False)
        path = Path(config_path or os.getenv("FACTORY_CONFIG", ROOT / "configs/local.json"))
        self.config = json.loads(path.read_text(encoding="utf-8-sig"))
        self.database_url = database_url or os.getenv("DATABASE_URL", "")
        if not self.database_url.startswith(("postgresql://", "postgres://")):
            raise ValueError("请先运行 scripts/setup_db.py 配置独立 PostgreSQL DATABASE_URL")
        self.runtime = (ROOT / self.config["runtime_dir"]).resolve()
        self.weights = (ROOT / self.config["weights"]).resolve()
        self.sources = {s["id"]: {**s, "path": (ROOT / s["path"]).resolve()} for s in self.config["sources"]}
        if len(self.sources) != len(self.config["sources"]):
            raise ValueError("配置中的 source id 重复")
        self.defaults = self.config["defaults"]
        self.runtime.mkdir(parents=True, exist_ok=True)

