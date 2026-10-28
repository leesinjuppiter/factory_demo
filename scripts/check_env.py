"""只读环境和配置检查，不加载权重、不安装依赖。"""
import importlib.metadata
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.settings import Settings
import psycopg
import torch

cfg = Settings()
packages = {name: importlib.metadata.version(name) for name in
            ("torch", "torchvision", "opencv-python", "fastapi", "uvicorn", "psycopg", "python-multipart")}
with psycopg.connect(cfg.database_url, connect_timeout=5) as conn:
    db, user = conn.execute("SELECT current_database(),current_user").fetchone()
print(json.dumps({"python": sys.executable, "packages": packages, "cuda_available": torch.cuda.is_available(),
                  "database": db, "database_role": user, "weights_exist": cfg.weights.is_file(),
                  "sources": {key: str(value["path"]) for key, value in cfg.sources.items()}}, ensure_ascii=False, indent=2))
