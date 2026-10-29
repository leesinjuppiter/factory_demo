"""Summarize retained benchmark traces; no changes to inference settings."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from benchmark_full4911 import signature


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def stats(values):
    data=np.asarray([float(value) for value in values if pd.notna(value) and np.isfinite(float(value))])
    if not len(data):return {'n':0}
    return dict(n=len(data),mean=float(data.mean()),p50=float(np.percentile(data,50)),p90=float(np.percentile(data,90)),
                p95=float(np.percentile(data,95)),p99=float(np.percentile(data,99)),minimum=float(data.min()),maximum=float(data.max()),sum=float(data.sum()))


def frame_table(rows,event,run_ids):
    items=[row for row in rows if row['event']==event and row.get('run_id') in run_ids]
    table=pd.DataFrame(items)
    if len(table):table['frame_id']=table['frame_id'].map(lambda value:str(int(value)))
    return table


def db_rows(run_map):
    import psycopg
    from dotenv import dotenv_values
    rows=[]
    with psycopg.connect(dotenv_values(ROOT/'.env')['DATABASE_URL']) as conn:
        conn.execute('SET TRANSACTION READ ONLY')
        for run_id,split in run_map.items():
            with conn.cursor(name='benchmark_'+split) as cursor:
                cursor.itersize=100
                cursor.execute('SELECT frame_id,data FROM factory_frames WHERE run_id=%s ORDER BY frame_id',(run_id,))
                for frame_id,data in cursor:
                    rows.append(dict(run_id=run_id,frame_id=str(frame_id),split=split,sha256=data.get('sha256'),
                                     saved_status=data['status'],class_counts=json.dumps(dict(Counter(str(d['class_id']) for d in data['detections']))),
                                     signature=signature(data['detections'])))
    return pd.DataFrame(rows)


def resource_summary(path,start,end):
    rows=[r for r in read_jsonl(path) if start<=r['mono_ns']<=end]
    result={'samples':len(rows),'interval_seconds':2,'cpu_percent_definition':'100% = one logical CPU, not the entire host'}
    result['process_cpu_percent']=stats(r['process_cpu_percent'] for r in rows if 'process_cpu_percent' in r)
    result['process_rss_mib']=stats(r['process']['rss_kib']/1024 for r in rows if r.get('process'))
    for name in ['util_percent','memory_util_percent','memory_mib','power_w','temperature_c']:
        result['gpu_'+name]=stats(r['gpu'][name] for r in rows if r.get('gpu'))
    if len(rows)>1:
        result['process_io_delta']={key:rows[-1]['process'].get(key,0)-rows[0]['process'].get(key,0) for key in ['rchar','wchar','read_bytes','write_bytes']}
    return result


def analyze(source,output):
    output.mkdir(parents=True,exist_ok=True)
    baseline_meta=json.loads((source/'baseline-result.json').read_text())
    pipeline_meta=json.loads((source/'pipeline-result.json').read_text())
    baseline=pd.read_csv(source/'baseline-frames.csv',dtype={'frame_id':str})
    baseline['run_id']='baseline_'+baseline['split']
    base_trace=read_jsonl(source/'baseline-trace.jsonl');trace=read_jsonl(source/'pipeline-trace.jsonl')
    assert base_trace[-1]['event']=='trace_overhead' and trace[-1]['event']=='trace_overhead','Trace must be explicitly flushed at shutdown'
    run_map={entry['run']['id']:entry['run']['source_id'].removeprefix('bench_') for entry in pipeline_meta['runs']}
    run_ids=set(run_map)
    base_adapter=frame_table(base_trace,'adapter',set(baseline['run_id']))
    assert len(base_adapter)==4911 and not base_adapter.duplicated(['run_id','frame_id']).any()
    extra=[key for key in base_adapter if key not in baseline or key in ['run_id','frame_id']]
    baseline=baseline.merge(base_adapter[extra],on=['run_id','frame_id'],how='left',validate='one_to_one')
    pipeline=frame_table(trace,'frame_cycle',run_ids)
    assert len(pipeline)==4911 and len(baseline)==4911
    for event in ['input','adapter']:
        table=frame_table(trace,event,run_ids)
        assert len(table)==4911 and not table.duplicated(['run_id','frame_id']).any(),event
        extra=[key for key in table if key not in pipeline or key in ['run_id','frame_id']]
        pipeline=pipeline.merge(table[extra],on=['run_id','frame_id'],how='left',validate='one_to_one')
    pipeline=pipeline.merge(db_rows(run_map),on=['run_id','frame_id'],how='left',validate='one_to_one')
    manifest=read_jsonl(source/'manifest.jsonl');identities={(r['split'],str(r['frame_id'])):r for r in manifest}
    pipeline['relative_path']=[identities[(r.split,r.frame_id)]['relative_path'] for r in pipeline.itertuples()]
    sha_matches=[r.sha256==identities[(r.split,r.frame_id)]['sha256'] for r in pipeline.itertuples()]
    assert all(sha_matches),'Saved input bytes differ from frozen manifest'
    previews=frame_table(trace,'preview',run_ids)
    preview_metrics=['run_id','frame_id']+[key for key in previews if key.endswith('_ms') or key in ['ready_ns','queued_ns','bytes','preview_id']]
    previews=previews[preview_metrics].rename(columns={key:'preview_'+key for key in preview_metrics if key not in ['run_id','frame_id']})
    pipeline=pipeline.merge(previews,on=['run_id','frame_id'],how='left',validate='one_to_one')
    observer=pd.DataFrame([row for row in read_jsonl(source/'local-observer.jsonl') if row.get('run_id') in run_ids])
    observer['frame_id']=observer['frame_id'].map(lambda value:str(int(value)))
    assert not observer.duplicated(['run_id','frame_id']).any()
    observer=observer.rename(columns={key:'observer_'+key for key in observer if key not in ['run_id','frame_id']})
    pipeline=pipeline.merge(observer,on=['run_id','frame_id'],how='left',validate='one_to_one')
    pipeline['frame_to_preview_ms']=(pipeline['preview_ready_ns']-pipeline['frame_start_ns'])/1e6
    pipeline['commit_to_preview_ms']=(pipeline['preview_ready_ns']-pipeline['db_committed_ns'])/1e6
    pipeline['frame_to_local_decode_ms']=(pipeline['observer_decoded_ns']-pipeline['frame_start_ns'])/1e6
    pipeline['observer_wait_ms']=(pipeline['observer_downloaded_ns']-pipeline['observer_http_ms']*1e6-pipeline['observer_received_ns'])/1e6
    send=frame_table(trace,'ws_send',run_ids)
    chosen=send[send['observer']==True][['revision','send_start_ns']].drop_duplicates('revision')
    pipeline=pipeline.merge(chosen,left_on='observer_revision',right_on='revision',how='left',validate='many_to_one')
    pipeline['ws_send_start_to_local_receive_ms']=(pipeline['observer_received_ns']-pipeline['send_start_ns'])/1e6
    joined=baseline[['relative_path','detections','class_counts','signature']].merge(pipeline[['relative_path','detections','class_counts','signature']],on='relative_path',suffixes=('_baseline','_pipeline'),validate='one_to_one')
    count_mismatch=joined['detections_baseline']!=joined['detections_pipeline']
    class_mismatch=[json.loads(a)!=json.loads(b) for a,b in zip(joined['class_counts_baseline'],joined['class_counts_pipeline'])]
    identity=dict(manifest_images=len(manifest),manifest_unique_sha256=len({r['sha256'] for r in manifest}),saved_sha256_matches=sum(sha_matches),detection_count_mismatches=int(count_mismatch.sum()),
                  class_count_mismatches=sum(class_mismatch),rounded_output_signature_mismatches=int((joined['signature_baseline']!=joined['signature_pipeline']).sum()),
                  note='Signature equality is diagnostic; this is not AP/recall or full floating-point equivalence verification')
    group_columns={
        '读取/哈希/解码':['stat_ms','file_read_ms','integrity_hash_ms','decode_ms'],
        '预处理与传输':['preprocess_ms'],
        '模型前向':['inference_ms'],
        '候选/NMS/坐标':['postprocess_ms','geometry_enrich_ms'],
        '原图快照写盘':['snapshot_write_ms'],
        '统计/数据库/发布':['space_check_ms','stats_copy_ms','db_commit_ms','publish_ms']}
    groups={}
    for name,columns in group_columns.items():
        values=pipeline[columns].sum(axis=1,min_count=len(columns));groups[name]=stats(values)
    assigned=sum((pipeline[columns].sum(axis=1,min_count=len(columns)) for columns in group_columns.values()))
    residual=pipeline['active_cycle_ms']-assigned
    groups['其他主链路开销']=stats(residual)
    assert residual.min()>-.01,'Main-stage accounting overlaps'
    pipeline['unattributed_active_ms']=residual
    pipeline.to_csv(output/'pipeline-frames.csv',index=False)
    baseline.to_csv(output/'baseline-frames.csv',index=False)
    pipeline_stages={column:stats(pipeline[column]) for column in pipeline if column.endswith('_ms')}
    base_stages={column:stats(baseline[column]) for column in baseline if column.endswith('_ms')}
    starts={r['run_id']:r['mono_ns'] for r in trace if r['event']=='run_start' and r.get('run_id') in run_ids}
    ends={r['run_id']:r['mono_ns'] for r in trace if r['event']=='run_end' and r.get('run_id') in run_ids}
    worker_seconds=sum((ends[key]-starts[key])/1e9 for key in run_ids)
    scenario_start=pipeline_meta['runs'][0]['request_start_ns'];scenario_end=pipeline_meta['runs'][-1]['observed_end_ns']
    scenario_seconds=(scenario_end-scenario_start)/1e9
    splits={}
    for split in ['train','val','test']:
        table=pipeline[pipeline['split']==split];base=baseline[baseline['split']==split];entry=next(e for e in pipeline_meta['runs'] if run_map[e['run']['id']]==split)
        seconds=(ends[entry['run']['id']]-starts[entry['run']['id']])/1e9
        splits[split]=dict(images=len(table),failed=int((table['status']!='ok').sum()),detections=int(table['detections'].sum()),
                           pipeline_worker_seconds=seconds,pipeline_worker_fps=len(table)/seconds,active_cycle_ms=stats(table['active_cycle_ms']),baseline_frame_ms=stats(base['frame_wall_ms']))
    budget=1000/42
    summary=dict(passed=bool(len(pipeline)==4911 and (pipeline['status']=='ok').all() and (baseline['status']=='ok').all()),
        environment=json.loads((source/'environment.json').read_text()),identity=identity,
        baseline=dict(processed=4911,failed=int((baseline['status']!='ok').sum()),wall_seconds=baseline_meta['wall_seconds'],fps=4911/baseline_meta['wall_seconds'],
                      detections=int(baseline['detections'].sum()),stages_ms=base_stages,load_wall_ms=baseline_meta['load_wall_ms'],warmup_wall_ms=baseline_meta['warmup_wall_ms'],gpu_peak_allocated_bytes=baseline_meta['gpu_peak_allocated_bytes']),
        pipeline=dict(processed=4911,failed=int((pipeline['status']!='ok').sum()),detections=int(pipeline['detections'].sum()),
                      empty_successful_frames=int((pipeline['detections']==0).sum()),max_det_reached_frames=int((pipeline['detections']>=300).sum()),
                      scenario_wall_seconds=scenario_seconds,scenario_fps=4911/scenario_seconds,worker_wall_seconds=worker_seconds,worker_fps=4911/worker_seconds,
                      stages_ms=pipeline_stages,main_groups_ms=groups,worker_unattributed_seconds=worker_seconds-pipeline['cycle_ms'].sum()/1000,
                      run_ids=list(run_map),effective_pacing='unpaced benchmark override; normal API cap remains 10fps',
                      database_before=pipeline_meta['database_before'],database_after=pipeline_meta['database_after'],
                      filesystem_free_delta=pipeline_meta['filesystem_free_before']-pipeline_meta['filesystem_free_after']),
        display=dict(previews=len(previews),missing_previews=4911-len(previews),observed_preview_images=len(observer),
                     observer_http_status_counts={str(k):int(v) for k,v in observer['observer_status'].value_counts().items()},
                     local_decode_latency_ms=stats(pipeline['frame_to_local_decode_ms']),
                     ws_send_ms=stats(send['send_ms']),ws_queue_copy_ms=stats(frame_table(trace,'ws_queue',run_ids)['lock_and_snapshot_ms']),
                     note='Latest-only preview/WS can skip display frames; missing observations are not zero latency and not detection loss'),
        splits=splits,budget_42fps=dict(frame_budget_ms=budget,active_cycle_exceeds_budget=int((pipeline['active_cycle_ms']>budget).sum()),
                     note='Reference budget only; input resolution differs from the planned industrial camera; no actuator/exposure deadline measured'),
        resources=dict(baseline=resource_summary(source/'baseline-resources.jsonl',baseline_meta['measure_start_ns'],baseline_meta['measure_end_ns']),
                       pipeline=resource_summary(source/'pipeline-resources.jsonl',scenario_start,scenario_end)),
        restoration=json.loads((source/'restoration.json').read_text()),
        host_environment=json.loads((source/'host-environment.json').read_text()),
        attempt_audit=json.loads((source/'attempt-audit.json').read_text()) if (source/'attempt-audit.json').exists() else None,
        observer_counters=json.loads((source/'observer-counters.json').read_text()) if (source/'observer-counters.json').exists() else None,
        trace_overhead=dict(baseline=[r for r in base_trace if r['event']=='trace_overhead'],pipeline=[r for r in trace if r['event']=='trace_overhead']),
        caveats=['single measured pass per condition; percentile variation reflects image mix, not repeat-run confidence intervals',
                 'record emit_wall_ms is summed across threads and cannot be subtracted from wall time as exact overhead',
                 'process CPU/RSS exclude PostgreSQL, gateway and observer; GPU utilization is whole-device sampled data',
                 'frame_to_preview/local_decode starts after space check; active_cycle starts before space check',
                 'all sources prehashed; no cold-cache disk claim','timers and one additional CUDA NMS sync add instrumentation overhead',
                 'main chain stages are disjoint; parallel preview/WS/local-consumer times must not be added to it',
                 'DB duration includes Python serialization, lock, SQL, local transport and commit; not server-only SQL time',
                 'snapshot write_bytes is page-cache write, not fsync durability latency','local consumer is not WAN or browser painting',
                 'train/val/test retained for performance only; no class mapping/AP/precision/recall evaluation'])
    (output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    rows=[]
    for phase,stages in [('baseline',base_stages),('pipeline',pipeline_stages)]:
        for name,values in stages.items():rows.append(dict(phase=phase,stage=name,**values))
    pd.DataFrame(rows).to_csv(output/'stage-statistics.csv',index=False)
    print(json.dumps({phase:{k:v for k,v in summary[phase].items() if k in ['processed','failed','wall_seconds','fps','scenario_wall_seconds','scenario_fps','worker_fps']} for phase in ['baseline','pipeline']}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--input',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();analyze(args.input,args.output)
