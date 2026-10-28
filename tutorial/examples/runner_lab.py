"""真实 Runner + 内存存储 + 教学适配器：验证控制流，不代表真实推理或数据库。"""
import argparse
import copy
import json
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
import cv2
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'reference'))
from backend.runner import Runner
from fake_adapter import TeachingAdapter
class MemoryStore:
    def __init__(self):self.runs={};self.frames={}
    def save_run(self,run):self.runs[run['id']]=copy.deepcopy(run)
    def save_frame(self,run,frame,image_path):
        self.frames[(run['id'],frame['id'])]={'data':copy.deepcopy(frame),'image_path':str(image_path)}
        self.save_run(run)
    def frame(self,r,f):return self.frames.get((r,f))
    def latest_run(self):return list(self.runs.values())[-1] if self.runs else None
def run_lab(base):
    folder=base/uuid.uuid4().hex;inputs=folder/'inputs';inputs.mkdir(parents=True)
    cv2.imwrite(str(inputs/'01.png'),np.zeros((32,48,3),dtype=np.uint8))
    cv2.imwrite(str(inputs/'02.png'),np.full((32,48,3),120,dtype=np.uint8))
    (inputs/'03.png').write_bytes(b'not a png')
    cfg=SimpleNamespace(weights=folder/'unused.pt',runtime=folder/'runtime',sources={'lesson':{'path':inputs,'label':'教学三张图'}})
    cfg.runtime.mkdir();store=MemoryStore();runner=Runner(cfg,store,TeachingAdapter)
    params={'source_id':'lesson','engine':'pytorch','confidence':.25,'iou':.45,'image_size':640,'max_det':300,'replay_fps':10}
    initial=runner.start(params);runner.thread.join(timeout=10)
    assert not runner.thread.is_alive(),'教学任务未结束'
    final=store.runs[initial['id']]
    assert (final['status'],final['processed'],final['succeeded'],final['failed'],final['detection_count'])==('completed',3,2,1,1)
    assert store.frames[(initial['id'],1)]['data']['detections']==[]
    assert store.frames[(initial['id'],3)]['data']['status']=='error'
    (inputs/'02.png').write_bytes(b'changed source')
    saved=Path(store.frames[(initial['id'],2)]['image_path'])
    assert saved.is_file() and cv2.imdecode(np.frombuffer(saved.read_bytes(),np.uint8),1) is not None
    runner.close()
    result={'mode':'teaching fake adapter + memory store','processed':3,'succeeded':2,'failed':1,'snapshots_survive_source_change':True,'folder':str(folder)}
    (folder/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--work-dir',type=Path,default=ROOT/'practice/lab-output');a=p.parse_args()
    print(json.dumps(run_lab(a.work_dir),ensure_ascii=False,indent=2))
