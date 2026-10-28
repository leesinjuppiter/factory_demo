"""不连接数据库、不导入模型、不安装依赖。"""
import importlib.metadata
import json
import sys
versions={}
for name in ['torch','torchvision','opencv-python','numpy','fastapi','uvicorn','psycopg','python-multipart','pytest','httpx']:
    try: versions[name]=importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError: versions[name]='MISSING'
print(json.dumps({'python':sys.executable,'version':sys.version,'packages':versions},ensure_ascii=False,indent=2))
