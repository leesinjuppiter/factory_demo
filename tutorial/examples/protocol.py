"""数据协议实验：这些坐标是教学示例，不是真实模型预测。"""
import json
import math
def validate(frame):
    assert frame['width']>0 and frame['height']>0
    for d in frame['detections']:
        assert 0<=d['confidence']<=1
        assert len(d['polygon'])==4
        assert all(len(p)==2 and all(math.isfinite(v) for v in p) for p in d['polygon'])
    return True
FRAME={'run_id':'lesson-only','id':1,'width':640,'height':360,'status':'ok','detections':[{'id':1,'class_id':0,'class_name':'example','confidence':0.9,'polygon':[[120,80],[240,100],[220,200],[100,180]]}]}
if __name__=='__main__':
    validate(FRAME)
    print(json.dumps(FRAME,ensure_ascii=False,indent=2))
    print('协议检查通过；置信度不是准确率，id 不是跟踪编号。')
