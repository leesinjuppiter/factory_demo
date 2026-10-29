"""Reproducible full-dataset baseline and real application benchmark (Linux)."""
import argparse
from collections import Counter
import csv
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import io
import json
import os
import queue
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import threading
import time

import httpx
from PIL import Image
from websockets.sync.client import connect

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
URL = 'http://127.0.0.1:8765'
PARAMS = dict(engine='pytorch', image_size=640, confidence=.25, iou=.45, max_det=300, replay_fps=10)
SPLITS = ('train', 'val', 'test')


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def progress(out, phase, count=0, **extra):
    write_json(out/'progress.json', dict(phase=phase, processed=count, utc=datetime.now(timezone.utc).isoformat(), **extra))


def signature(detections):
    values = [(d['class_id'], round(d['confidence'], 6), [[round(v, 3) for v in p] for p in d['polygon']]) for d in detections]
    return hashlib.sha256(json.dumps(values, separators=(',', ':')).encode()).hexdigest()


def database_metrics():
    import psycopg
    from dotenv import dotenv_values
    with psycopg.connect(dotenv_values(ROOT/'.env')['DATABASE_URL']) as conn:
        row=conn.execute("SELECT pg_database_size(current_database()), pg_current_wal_lsn()::text, version(), current_setting('synchronous_commit'), current_setting('fsync'), current_setting('track_io_timing')").fetchone()
    return dict(bytes=row[0],wal_lsn=row[1],version=row[2],synchronous_commit=row[3],fsync=row[4],track_io_timing=row[5])


def prepare(dataset, out):
    from backend.images import inventory
    rows = []
    for split in SPLITS:
        for index, item in enumerate(inventory(dataset/split/'images'), 1):
            path=item['path'];data=path.read_bytes()
            assert path.stat().st_mtime_ns==item['mtime']
            with Image.open(io.BytesIO(data)) as image: width,height=image.size
            rows.append(dict(split=split, frame_id=index, path=str(path), relative_path=str(path.relative_to(dataset)),
                             bytes=len(data), mtime_ns=item['mtime'], sha256=hashlib.sha256(data).hexdigest(), width=width, height=height))
    assert len(rows)==4911, f'Expected 4911 files, found {len(rows)}'
    manifest=out/'manifest.jsonl'
    assert not manifest.exists(), 'Refuse to overwrite an existing benchmark manifest'
    manifest.write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in rows),encoding='utf-8')
    warm=rows[:10].copy();shapes={(r['width'],r['height']) for r in warm}
    for row in rows:
        shape=(row['width'],row['height'])
        if shape not in shapes: warm.append(row);shapes.add(shape)
    warm_dir=out/'warm_images';warm_dir.mkdir()
    for index,row in enumerate(warm): shutil.copy2(row['path'],warm_dir/f'{index:04d}{Path(row["path"]).suffix}')
    config=json.loads((ROOT/'configs/cloud.json').read_text())
    config['sources']=[dict(id='bench_warmup',label='Benchmark warm-up (excluded)',path=str(warm_dir))]+[
        dict(id='bench_'+split,label=f'完整4911 · {split}',path=str(dataset/split/'images')) for split in SPLITS]
    write_json(out/'benchmark-config.json',config)
    packages={}
    for name in ['torch','torchvision','numpy','opencv-python','Pillow','fastapi','uvicorn','websockets','psycopg','python-dotenv']:
        packages[name]=metadata.version(name)
    files=['backend/profiling.py','backend/runner.py','backend/presentation.py','backend/app.py','backend/inference/pytorch_obb.py','scripts/benchmark_full4911.py']
    info=dict(python=sys.executable,python_version=sys.version,packages=packages,parameters=PARAMS,batch=1,precision='float32',device='cuda:0',
              split_counts=dict(Counter(r['split'] for r in rows)),source_bytes=sum(r['bytes'] for r in rows),
              resolution_counts=dict(Counter(f'{r["width"]}x{r["height"]}' for r in rows)),warmup_images=len(warm),
              manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
              code_base_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
              source_hashes={name:hashlib.sha256((ROOT/name).read_bytes().replace(b'\r\n',b'\n')).hexdigest() for name in files},
              cache_policy='All input bytes hashed before timing; no OS cache flush; warm-cache-oriented, not cold disk throughput',
              timing_policy='perf_counter_ns wall times; existing CUDA sync plus one extra NMS-boundary sync while tracing',
              limitations=['one measured pass per condition, not repeat-run variance','no accuracy/AP assessment','source files already on disk; no real exposure or actuator timing','local HTTP/JPEG observer is not a browser paint or WAN measurement'])
    write_json(out/'environment.json',info)
    return rows


def sample_process(pid):
    try:
        base=Path('/proc')/str(pid)
        fields=(base/'stat').read_text().rsplit(')',1)[1].split()
        status={line.split(':')[0]:line.split(':',1)[1].strip() for line in (base/'status').read_text().splitlines() if ':' in line}
        disk={line.split(':')[0]:int(line.split(':')[1]) for line in (base/'io').read_text().splitlines()}
        return dict(ticks=int(fields[11])+int(fields[12]),rss_kib=int(status['VmRSS'].split()[0]),threads=int(status['Threads']),**disk)
    except (OSError,KeyError):return {}


class Monitor:
    def __init__(self,out,phase,pid):
        self.out,self.phase,self.pid=out,phase,pid;self.stop=threading.Event()
        self.thread=threading.Thread(target=self.work,daemon=True);self.thread.start()
    def work(self):
        previous=None;last=None
        with (self.out/f'{self.phase}-resources.jsonl').open('w') as stream:
            while not self.stop.is_set():
                now=time.perf_counter_ns();process=sample_process(self.pid)
                row=dict(mono_ns=now,phase=self.phase,pid=self.pid,process=process)
                if previous and process and last:
                    row['process_cpu_percent']=(process['ticks']-previous['ticks'])/os.sysconf('SC_CLK_TCK')/((now-last)/1e9)*100
                try:
                    gpu=subprocess.check_output(['nvidia-smi','--query-gpu=utilization.gpu,utilization.memory,memory.used,power.draw,temperature.gpu','--format=csv,noheader,nounits'],text=True,timeout=4).strip()
                    row['gpu']=dict(zip(['util_percent','memory_util_percent','memory_mib','power_w','temperature_c'],[float(x.strip()) for x in gpu.split(',')]))
                except Exception as exc:row['gpu_error']=type(exc).__name__
                stream.write(json.dumps(row)+'\n');stream.flush();previous,last=process,now
                self.stop.wait(2)
    def close(self):self.stop.set();self.thread.join(6)


def baseline(out, rows):
    from backend.images import decode
    from backend.contracts import detection_view
    from backend.inference.pytorch_obb import PytorchOBBAdapter
    from backend import profiling
    adapter=PytorchOBBAdapter(ROOT/'vendor/weights/factory_now.pt',device='cuda:0')
    load_start=time.perf_counter_ns();model=adapter.load();load_done=time.perf_counter_ns()
    for index,path in enumerate(sorted((out/'warm_images').iterdir()),1):
        profiling.set_frame('warmup_baseline',index)
        adapter.predict(decode(path.read_bytes()),**{k:PARAMS[k] for k in ['image_size','confidence','iou','max_det']})
    adapter.torch.cuda.reset_peak_memory_stats(adapter.device)
    started=time.perf_counter_ns();success=failed=boxes=0
    fields=['split','frame_id','relative_path','status','error','detections','class_counts','signature','file_stat_ms','file_read_ms','integrity_hash_ms','decode_ms','preprocess_ms','inference_ms','postprocess_ms','geometry_enrich_ms','frame_wall_ms']
    with (out/'baseline-frames.csv').open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for index,item in enumerate(rows,1):
            profiling.set_frame('baseline_'+item['split'],item['frame_id'])
            row=dict(split=item['split'],frame_id=item['frame_id'],relative_path=item['relative_path'],status='ok',error='')
            t0=time.perf_counter_ns()
            try:
                path=Path(item['path']);stat=path.stat();t1=time.perf_counter_ns()
                assert stat.st_mtime_ns==item['mtime_ns'] and stat.st_size==item['bytes']
                data=path.read_bytes();t2=time.perf_counter_ns()
                assert hashlib.sha256(data).hexdigest()==item['sha256'];t3=time.perf_counter_ns()
                image=decode(data);t4=time.perf_counter_ns()
                result=adapter.predict(image,**{k:PARAMS[k] for k in ['image_size','confidence','iou','max_det']})
                geom=time.perf_counter_ns()
                for detection in result['detections']: detection_view(detection)
                done=time.perf_counter_ns()
                row.update(detections=len(result['detections']),class_counts=json.dumps(dict(Counter(d['class_id'] for d in result['detections']))),signature=signature(result['detections']),
                           file_stat_ms=(t1-t0)/1e6,file_read_ms=(t2-t1)/1e6,integrity_hash_ms=(t3-t2)/1e6,decode_ms=(t4-t3)/1e6,
                           geometry_enrich_ms=(done-geom)/1e6,**{k+'_ms':v for k,v in result['timing_ms'].items()})
                success+=1;boxes+=row['detections']
            except Exception as exc:
                row.update(status='error',error=type(exc).__name__+': '+str(exc));failed+=1
            row['frame_wall_ms']=(time.perf_counter_ns()-t0)/1e6
            writer.writerow(row)
            if index%100==0 or index==len(rows):progress(out,'baseline',index,failed=failed,elapsed_seconds=(time.perf_counter_ns()-started)/1e9)
    ended=time.perf_counter_ns()
    write_json(out/'baseline-result.json',dict(measure_start_ns=started,measure_end_ns=ended,wall_seconds=(ended-started)/1e9,
               processed=len(rows),succeeded=success,failed=failed,detections=boxes,model=model,load_wall_ms=(load_done-load_start)/1e6,warmup_wall_ms=(started-load_done)/1e6,
               gpu_peak_allocated_bytes=adapter.torch.cuda.max_memory_allocated(adapter.device),gpu_peak_reserved_bytes=adapter.torch.cuda.max_memory_reserved(adapter.device)))
    profiling.close()


def wait_healthy(client):
    for _ in range(100):
        try:
            response=client.get('/api/health');response.raise_for_status();return
        except (httpx.HTTPError,ValueError):time.sleep(.2)
    raise RuntimeError('Application failed to become healthy')


def stop_service(pid):
    proc=Path('/proc')/str(pid)
    assert proc.joinpath('cwd').resolve()==ROOT and b'start.py' in proc.joinpath('cmdline').read_bytes()
    os.kill(pid,signal.SIGTERM)
    for _ in range(150):
        try:
            with httpx.Client(base_url=URL,trust_env=False,timeout=.3) as client:client.get('/api/health')
        except httpx.HTTPError:
            state=proc/'stat'
            if not state.exists() or state.read_text().rsplit(')',1)[1].split()[0]=='Z':return
        time.sleep(.1)
    raise RuntimeError('Service did not stop; refusing a second instance')


def start_service(out,trace=False):
    env=os.environ.copy()
    for key in ['FACTORY_CONFIG','FACTORY_TRACE_PATH','FACTORY_BENCHMARK_UNPACED']:env.pop(key,None)
    env.update(FACTORY_DEVICE='cuda:0',PYTHONDONTWRITEBYTECODE='1')
    if trace:env.update(FACTORY_CONFIG=str(out/'benchmark-config.json'),FACTORY_TRACE_PATH=str(out/'pipeline-trace.jsonl'),FACTORY_BENCHMARK_UNPACED='1')
    with (out/'service.log').open('a') as log:
        process=subprocess.Popen([sys.executable,'-B','start.py'],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    (ROOT.parent/'tmp/factory-cloud-20261028/service.pid').write_text(str(process.pid))
    return process


class Observer:
    def __init__(self,out):
        self.out=out;self.stop=threading.Event();self.ready=threading.Event()
        self.thread=threading.Thread(target=self.work,daemon=True);self.thread.start()
    def work(self):
        pending=queue.Queue(maxsize=1);consumer_stop=threading.Event()
        counters={'unique_previews':0,'replaced_pending':0,'downloaded':0}
        with (self.out/'local-observer.jsonl').open('w') as stream:
            def consume():
                with httpx.Client(base_url=URL,trust_env=False,timeout=10) as client:
                    while not consumer_stop.is_set() or not pending.empty():
                        try:item,preview=pending.get(timeout=.2)
                        except queue.Empty:continue
                        try:
                            started=time.perf_counter_ns();response=client.get(preview['url']);downloaded=time.perf_counter_ns()
                            item.update(status=response.status_code,bytes=len(response.content),http_ms=(downloaded-started)/1e6,downloaded_ns=downloaded)
                            if response.status_code==200:
                                with Image.open(io.BytesIO(response.content)) as image:image.load()
                                item.update(decoded_ns=time.perf_counter_ns(),decode_ms=(time.perf_counter_ns()-downloaded)/1e6)
                        except Exception as exc:item['error']=type(exc).__name__
                        stream.write(json.dumps(item)+'\n');stream.flush();counters['downloaded']+=1
            consumer=threading.Thread(target=consume,daemon=True);consumer.start()
            try:
                with connect('ws://127.0.0.1:8765/api/display/ws',origin=URL,additional_headers={'X-Benchmark-Observer':'1'},max_size=2**20,max_queue=1) as ws:
                    self.ready.set();seen=set()
                    while not self.stop.is_set():
                        try:packet=json.loads(ws.recv(timeout=1))
                        except TimeoutError:continue
                        received=time.perf_counter_ns();frame=packet.get('frame') or {};preview=frame.get('preview')
                        if not preview or preview['id'] in seen:continue
                        seen.add(preview['id'])
                        item=dict(run_id=frame['stream_session_id'],frame_id=frame['id'],revision=packet['revision'],preview_id=preview['id'],received_ns=received)
                        counters['unique_previews']+=1
                        try:pending.put_nowait((item,preview))
                        except queue.Full:
                            try:pending.get_nowait();counters['replaced_pending']+=1
                            except queue.Empty:pass
                            pending.put_nowait((item,preview))
            except Exception as exc:write_json(self.out/'observer-error.json',{'error':str(exc)})
            finally:
                consumer_stop.set();consumer.join(15);assert not consumer.is_alive()
                write_json(self.out/'observer-counters.json',counters)
    def close(self):
        self.stop.set();self.thread.join(30)
        assert not self.thread.is_alive(),'Observer did not finish'


def pipeline(out):
    with httpx.Client(base_url=URL,trust_env=False,timeout=10) as client:
        run=client.get('/api/status').json().get('run')
        assert not run or run['status'] in {'completed','stopped','failed','interrupted'}
    old_pid=int((ROOT.parent/'tmp/factory-cloud-20261028/service.pid').read_text())
    result={'runs':[],'warmup':None,'database_before':database_metrics(),'filesystem_free_before':shutil.disk_usage(ROOT).free}
    process=None;monitor=observer=None
    stop_service(old_pid)
    try:
        process=start_service(out,trace=True)
        with httpx.Client(base_url=URL,trust_env=False,timeout=30) as client:
            wait_healthy(client)
            observer=Observer(out);assert observer.ready.wait(10),'Local observer could not connect'
            monitor=Monitor(out,'pipeline',process.pid)
            for source in ['bench_warmup']+['bench_'+s for s in SPLITS]:
                started=time.perf_counter_ns()
                response=client.post('/api/runs',json=dict(PARAMS,source_id=source));response.raise_for_status();run_id=response.json()['id']
                deadline=time.monotonic()+3600
                while time.monotonic()<deadline:
                    response=client.get('/api/runs/'+run_id);response.raise_for_status();run=response.json()
                    progress(out,'pipeline',sum(r['run']['processed'] for r in result['runs'])+(0 if source=='bench_warmup' else run['processed']),source=source,run_id=run_id,run_processed=run['processed'],run_total=run['total'])
                    if run['status'] in {'completed','stopped','failed','interrupted'}:break
                    time.sleep(.5)
                else:raise RuntimeError('Pipeline timed out')
                ended=time.perf_counter_ns()
                assert run['status']=='completed',run.get('error')
                entry=dict(run=run,request_start_ns=started,observed_end_ns=ended,api_wall_seconds=(ended-started)/1e9)
                if source=='bench_warmup':result['warmup']=entry
                else:result['runs'].append(entry)
            time.sleep(2)
            result['display_end']=client.get('/api/display/snapshot').json()['service']
            result['database_after']=database_metrics()
            result['filesystem_free_after']=shutil.disk_usage(ROOT).free
            write_json(out/'pipeline-result.json',result)
    finally:
        def restore():
            if process and process.poll() is None:stop_service(process.pid)
            restored=start_service(out,trace=False)
            with httpx.Client(base_url=URL,trust_env=False,timeout=5) as client:
                wait_healthy(client)
                assert client.get('/api/health').status_code==200
            write_json(out/'restoration.json',dict(pid=restored.pid,trace_enabled=False,unpaced_enabled=False,config='configs/cloud.json',health='ok'))
        with ExitStack() as cleanup:
            cleanup.callback(restore)
            if monitor:cleanup.callback(monitor.close)
            if observer:cleanup.callback(observer.close)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,default=ROOT.parent/'dataset/dataset4911_obb_622')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--phase',choices=['all','baseline','pipeline'],default='all')
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    if args.phase=='baseline':
        rows=[json.loads(line) for line in (out/'manifest.jsonl').read_text().splitlines()]
        baseline(out,rows);return
    if args.phase=='pipeline':
        try:
            pipeline(out);progress(out,'measured_complete',4911)
        except Exception as exc:
            progress(out,'failed',error=type(exc).__name__+': '+str(exc));raise
        return
    try:
        progress(out,'preparing')
        rows=prepare(args.dataset.resolve(),out)
        progress(out,'baseline_start')
        env=os.environ.copy();env.update(FACTORY_TRACE_PATH=str(out/'baseline-trace.jsonl'),PYTHONDONTWRITEBYTECODE='1')
        with (out/'baseline.log').open('w') as log:
            child=subprocess.Popen([sys.executable,'-B',str(Path(__file__).resolve()),'--phase','baseline','--output',str(out)],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
            monitor=Monitor(out,'baseline',child.pid)
            try:code=child.wait()
            finally:monitor.close()
        assert code==0,'Baseline worker failed; inspect baseline.log'
        progress(out,'pipeline_start')
        pipeline(out)
        progress(out,'measured_complete',4911)
    except Exception as exc:
        progress(out,'failed',error=type(exc).__name__+': '+str(exc))
        raise


if __name__=='__main__':main()
