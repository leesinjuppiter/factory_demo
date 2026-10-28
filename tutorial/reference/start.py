"""教学练习入口：8876端口，不操作原工作台。"""
import os
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
temp = ROOT / "runtime" / "tmp"
temp.mkdir(parents=True, exist_ok=True)
os.environ["TEMP"] = os.environ["TMP"] = str(temp)
os.environ.setdefault("MPLCONFIGDIR", str(temp / "matplotlib"))
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app:app", host="127.0.0.1", port=8876, workers=1)
