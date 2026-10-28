"""汇集本次验收材料（仅限已知输入，不收集.env或数据库凭据）。"""
import importlib.metadata
import json
import platform
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = ROOT.parent / "tmp/20261028-factory-demo-01a180ab"
OUT = ROOT / "docs/evidence"
OUT.mkdir(parents=True, exist_ok=True)
for source, target in [(TMP / "smoke50.json", "smoke50.json"),
                       (TMP / "inference/parity.json", "detect-parity.json"),
                       (TMP / "inference/smoke.json", "inference-smoke.json"),
                       (TMP / "restart-result.json", "restart-result.json"),
                       (TMP / "pytest-final.log", "pytest-final.log")]:
    shutil.copyfile(source, OUT / target)
environment = {"python": sys.executable, "python_version": sys.version, "platform": platform.platform(),
               "packages": {d.metadata["Name"]: d.version for d in importlib.metadata.distributions()},
               "database": "factory_demo", "role": "factory_demo", "runtime": "PyTorch CPU FP32, 4 threads, batch 1"}
(OUT / "environment.json").write_text(json.dumps(environment, ensure_ascii=False, indent=2), encoding="utf-8")
summary = json.loads((OUT / "smoke50.json").read_text(encoding="utf-8"))
for run in summary["runs"]:
    print(run["source_id"], run["processed"], run["detection_count"], json.dumps(run["timings"]))
print(f"Evidence: {OUT}")
