"""通过真实HTTP执行三个子集（总50张），不训练、不计算精度。"""
import argparse
import json
import time
from pathlib import Path

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--sources", nargs="+", default=["smoke_test", "smoke_val", "smoke_train"])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=600)
    args = parser.parse_args()
    report = {"purpose": "真实推理/HTTP/PostgreSQL流程验收，非准确率评测", "runs": [], "passed": False}
    with httpx.Client(base_url=args.url, timeout=30, trust_env=False) as client:
        client.get("/api/health").raise_for_status()
        for source in args.sources:
            result = client.post("/api/runs", json={"source_id": source, "replay_fps": 10})
            result.raise_for_status()
            run_id = result.json()["id"]
            until = time.monotonic() + args.timeout
            while time.monotonic() < until:
                run = client.get(f"/api/runs/{run_id}").json()
                if run["status"] in {"completed", "stopped", "failed", "interrupted"}:
                    break
                time.sleep(.5)
            else:
                raise RuntimeError(f"任务超时：{run_id}")
            assert run["status"] == "completed" and run["processed"] == run["total"] and run["failed"] == 0, run
            exported = client.get(f"/api/runs/{run_id}/export").json()
            assert len(exported["frames"]) == run["total"]
            assert sum(len(f["detections"]) for f in exported["frames"]) == run["detection_count"]
            frame = exported["frames"][0]
            client.get(frame["image_url"]).raise_for_status()
            client.get(frame["annotated_url"]).raise_for_status()
            report["runs"].append(run)
            print(f"{source}: {run['processed']}张，{run['detection_count']}框，mean={run['timings']['mean_ms']:.2f}ms", flush=True)
        report["capabilities"] = client.get("/api/capabilities").json()
    report["passed"] = True
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"验收记录：{args.output}")


if __name__ == "__main__":
    main()
