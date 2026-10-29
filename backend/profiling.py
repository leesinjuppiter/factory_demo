"""Opt-in benchmark traces; normal runs create no trace file."""
import atexit
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import threading
from time import perf_counter_ns

_lock = threading.Lock()
_context = threading.local()
_file = None
_path = None
_records = _emit_ns = 0


def enabled():
    return bool(os.getenv("FACTORY_TRACE_PATH"))


def unpaced():
    return enabled() and os.getenv("FACTORY_BENCHMARK_UNPACED") == "1"


def set_frame(run_id, frame_id):
    _context.run_id, _context.frame_id = run_id, frame_id


def record(event, **values):
    global _file, _path, _records, _emit_ns
    path = os.getenv("FACTORY_TRACE_PATH")
    if not path:
        return
    started = perf_counter_ns()
    payload = {"event": event, "mono_ns": started,
               "utc": datetime.now(timezone.utc).isoformat(),
               "run_id": getattr(_context, "run_id", None),
               "frame_id": getattr(_context, "frame_id", None), **values}
    with _lock:
        if _path != path:
            if _file:
                _file.close()
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            _file = open(path, "a", encoding="utf-8", buffering=128*1024)
            _path = path
        _file.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
        _records += 1
        if _records % 25 == 0:
            _file.flush()
        _emit_ns += perf_counter_ns() - started


def close():
    global _file, _path
    with _lock:
        if _file:
            _file.write(json.dumps({"event": "trace_overhead", "records": _records,
                                    "emit_wall_ms": _emit_ns/1e6}) + "\n")
            _file.close()
            _file = _path = None


atexit.register(close)
