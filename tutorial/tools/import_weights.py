"""学习者主动导入已知可信权重；不反序列化，不下载，不覆盖不同文件。"""
import argparse
import hashlib
import shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
EXPECTED='62af01dbc971d332ad4813d5f2811243f555877ffbdb0755fe428159687ef037'
def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source',type=Path,required=True);args=parser.parse_args()
    src=args.source.resolve();target=ROOT/'practice/factory_demo/vendor/weights/factory_now.pt'
    if not src.is_file() or digest(src)!=EXPECTED:raise SystemExit('权重不存在或与本课程已验证权重哈希不同；未复制')
    if target.exists():
        if digest(target)!=EXPECTED:raise SystemExit('目标存在不同权重，拒绝覆盖')
        print('目标权重一致，无需复制')
    else:
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,target)
        if digest(target)!=EXPECTED:raise SystemExit('复制后的哈希不一致，请检查磁盘')
        print('可信权重已复制到练习项目；未加载模型')
