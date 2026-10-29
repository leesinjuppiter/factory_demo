"""Offline analysis of retained full4911 records; no model, database or network access."""
from pathlib import Path
import json
import pandas as pd

OUT=Path(__file__).resolve().parent
p=pd.read_csv(OUT/'pipeline-frames.csv');b=pd.read_csv(OUT/'baseline-frames.csv')
assert len(p)==len(b)==4911
summary=json.loads((OUT/'summary.json').read_text(encoding='utf-8'))
service_fps=summary['pipeline']['scenario_fps']
for column,stats in summary['pipeline']['stages_ms'].items():
 assert int(p[column].count())==stats['n'],column
 assert abs(float(p[column].mean())-stats['mean'])<1e-6,column
 assert abs(float(p[column].quantile(.95))-stats['p95'])<1e-6,column
common=['file_read_ms','integrity_hash_ms','decode_ms','preprocess_ms','inference_ms','postprocess_ms','geometry_enrich_ms']
comparison={k:{'baseline_mean':float(b[k].mean()),'pipeline_mean':float(p[k].mean()),'difference_ms':float(p[k].mean()-b[k].mean())} for k in common}
long=p[p.active_cycle_ms>100].copy()
long_columns=['file_read_ms','decode_ms','inference_ms','space_check_ms','db_commit_ms','snapshot_write_ms','stats_copy_ms','publish_ms']
long['largest_listed_stage']=long[long_columns].idxmax(axis=1)
windows={}
for split in ['train','val','test']:
 rows=p[p.split==split].sort_values('frame_id');n=len(rows)//5
 cols=['stats_copy_ms','db_commit_ms','inference_ms','decode_ms','active_cycle_ms']
 windows[split]={period:{k:float(data[k].mean()) for k in cols} for period,data in [('first20pct',rows.head(n)),('last20pct',rows.tail(n))]}
preview_bytes=p.preview_bytes
extra={'analysis_date':'2026-10-29','comparison_ms':comparison,
       'active_cycle_gt100ms':{'frames':len(long),'largest_listed_stage_counts':{k:int(v) for k,v in long.largest_listed_stage.value_counts().items()},'definition':'Largest measured stage among listed columns; correlation/attribution clue, not root-cause proof'},
       'split_windows':windows,'jpeg_bytes':{'mean':float(preview_bytes.mean()),'p95':float(preview_bytes.quantile(.95)),'max':int(preview_bytes.max())},
       'fixed_service_arrival42fps':{'arrival_fps':42,'observed_scenario_service_fps':service_fps,'backlog_growth_frames_per_second':42-service_fps,'excess_frames_per_minute':(42-service_fps)*60,'assumption':'Same input workload and sustained service rate; illustrative queue arithmetic, not measured camera experiment'},
       'limitations':['No repeated runs or no-preview paired condition; differences cannot isolate preview causality','Finite directory statistics use an increasing list; continuous inbox uses a capped deque of 1000, so do not transpose long-run scaling directly','Stage largest-value counts are descriptive, not evidence of disk/SQL root cause']}
(OUT/'additional-analysis.json').write_text(json.dumps(extra,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(extra,ensure_ascii=False,indent=2))
