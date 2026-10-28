"""使用指定Conda解释器运行本机单实例服务。"""
import os
import sys
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
# 库缓存与临时上传不写工作区根目录。
temp = ROOT.parent / "tmp" / datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d-factory-demo-runtime") / str(os.getpid())
temp.mkdir(parents=True, exist_ok=True)
os.environ["TEMP"] = os.environ["TMP"] = str(temp)
os.environ.setdefault("MPLCONFIGDIR", str(temp / "matplotlib"))
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app:app", host="127.0.0.1", port=8765, workers=1, log_level="info")
