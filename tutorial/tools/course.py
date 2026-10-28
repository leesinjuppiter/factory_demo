"""可选的参考文件放置工具。只写课程 practice，不覆盖已经修改的文件。"""
import argparse
import shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'reference'
TARGET=ROOT/'practice/factory_demo'
STAGES={
  1:['requirements-api.txt','.gitignore'],
  4:['frontend/admin.html','frontend/package.json','frontend/package-lock.json','frontend/vite.config.js','frontend/index.html'],
  6:['backend/__init__.py','backend/settings.py','backend/images.py','backend/acquisition.py','scripts/simulate_camera.py','configs/local.json','.env.example'],
  7:['backend/store.py','scripts/setup_db.py'],
  8:['backend/runner.py','backend/contracts.py','backend/presentation.py','backend/inference/__init__.py','backend/inference/factory.py'],
  9:['backend/app.py','start.py','start.cmd','start.ps1'],
  11:['backend/inference/'],
  12:['vendor/'],
  13:['frontend/src/components/DetectionStage.vue','frontend/src/stream/'],
  14:['frontend/src/'],
  16:['tests/','frontend/tests/','scripts/check_env.py','scripts/smoke.py','scripts/mock_display.py'],
}

def apply(stage):
    TARGET.mkdir(parents=True,exist_ok=True)
    files=[]
    for key,patterns in STAGES.items():
        if key>stage:continue
        for pattern in patterns:
            p=SOURCE/pattern
            files.extend(x for x in p.rglob('*') if x.is_file() and '__pycache__' not in x.parts) if p.is_dir() else files.append(p)
    added=same=0;preserved=[]
    for p in sorted(set(files)):
        target=TARGET/p.relative_to(SOURCE)
        if not target.resolve().is_relative_to(TARGET.resolve()):raise ValueError('目标超出练习目录')
        if target.exists():
            if target.read_bytes()!=p.read_bytes():preserved.append(str(target.relative_to(TARGET)))
            else:same+=1
            continue
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target);added+=1
    print(f'练习目录：{TARGET}\n新增 {added} 个文件，相同 {same} 个文件。')
    if preserved:print('保留你的修改，未覆盖：\n'+'\n'.join(preserved))
    print('文件放置不代表学习完成或运行通过；按每节验收项自行验证。')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['apply'])
    parser.add_argument('stage',type=int,choices=range(20))
    args=parser.parse_args();apply(args.stage)
