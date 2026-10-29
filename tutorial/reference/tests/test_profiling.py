import json
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import profiling


def test_disabled_profiler_never_creates_file(monkeypatch):
    monkeypatch.delenv('FACTORY_TRACE_PATH', raising=False)
    monkeypatch.setenv('FACTORY_BENCHMARK_UNPACED', '1')
    assert not profiling.enabled() and not profiling.unpaced()
    profiling.record('disabled')


def test_opt_in_trace_keeps_thread_frame_identity_and_flushes(tmp_path, monkeypatch):
    target = tmp_path / 'trace.jsonl'
    monkeypatch.setenv('FACTORY_TRACE_PATH', str(target))
    monkeypatch.setenv('FACTORY_BENCHMARK_UNPACED', '1')
    assert profiling.unpaced()
    def worker(index):
        profiling.set_frame('run', index)
        profiling.record('frame', duration_ms=0)
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
    for thread in threads: thread.start()
    for thread in threads: thread.join()
    profiling.close()
    rows = [json.loads(line) for line in target.read_text().splitlines()]
    frames = [row for row in rows if row['event'] == 'frame']
    assert sorted(row['frame_id'] for row in frames) == list(range(4))
    assert all(row['run_id'] == 'run' and row['duration_ms'] == 0 and row['mono_ns'] > 0 for row in frames)
    assert rows[-1]['event'] == 'trace_overhead'
