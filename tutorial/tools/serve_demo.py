"""仅学习者手工启动：真实 API/数据库 + 明确标注的教学适配器。"""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'practice/factory_demo'))
sys.path.insert(0,str(ROOT/'examples'))
from backend.app import create_app
from fake_adapter import TeachingAdapter
if __name__=='__main__':
    import uvicorn
    print('教学替身模式：结果不是模型预测。结束后按 Ctrl+C，再启动练习 start.py 切换真实模型。')
    uvicorn.run(create_app(adapter_factory=TeachingAdapter),host='127.0.0.1',port=8876,workers=1)
