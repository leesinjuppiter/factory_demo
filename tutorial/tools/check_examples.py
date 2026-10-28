"""验证教学例子，不连接 PostgreSQL、不启动服务、不加载真实权重。"""
import ast
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'examples'))
from fastapi.testclient import TestClient
from api_minimal import app
from protocol import FRAME,validate

def main():
    checked=[]
    for p in list((ROOT/'reference').rglob('*.py'))+list((ROOT/'examples').glob('*.py'))+list((ROOT/'tools').glob('*.py')):
        ast.parse(p.read_text(encoding='utf-8-sig'),filename=str(p));checked.append(str(p.relative_to(ROOT)))
    assert validate(FRAME)
    invalid={**FRAME,'detections':[{'confidence':.9,'polygon':[[float('nan'),0]]*4}]}
    try:validate(invalid)
    except AssertionError:pass
    else:raise AssertionError('非有限坐标应失败')
    with TestClient(app) as client:
        assert client.get('/api/health').json()['mode']=='teaching-only'
        assert client.post('/api/runs',json={'source_id':'example','confidence':.25}).status_code==201
        assert client.post('/api/runs',json={'source_id':'example','confidence':2}).status_code==422
    print(json.dumps({'python_syntax_files':len(checked),'protocol_valid_and_invalid':True,'minimal_api_200_201_422':True,'mode':'No database / No model'},ensure_ascii=False))

if __name__=='__main__':main()
