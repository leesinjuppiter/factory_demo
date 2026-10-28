"""Protocol, preview isolation and runtime state tests; no PostgreSQL or model."""
import asyncio
import copy
import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.contracts import detection_view, frame_view, stream_view
from backend.presentation import Presentation
from backend.runner import Runner


def until(predicate, timeout=4):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(.005)
    raise AssertionError("condition timed out")


def sample():
    run = {"id": "run-a", "source_id": "camera", "source_label": "测试来源", "status": "running",
           "total": None, "processed": 1, "succeeded": 1, "failed": 0, "class_counts": {"0": 1},
           "config": {"engine": "pytorch"}, "timings": {"mean_ms": None}, "error": None,
           "model": {"name": "test", "path": "C:/private/model.pt", "sha256": "sha", "box_type": "obb",
                     "classes": [{"id": 0, "name": "coal", "label": "煤", "color": "#00ffaa"}], "device": "cpu"}}
    frame = {"id": 1, "run_id": "run-a", "name": "one.png", "width": 48, "height": 32,
             "status": "ok", "created_at": "2026-10-28T00:00:00Z", "timing_ms": {}, "error": None,
             "image_url": "/internal-path", "detections": [{"id": 1, "class_id": 0, "class_name": "coal", "confidence": 0,
                "polygon": [[2, 2], [22, 2], [22, 12], [2, 12]]}]}
    return run, frame


def test_contract_preserves_zero_geometry_identity_and_hides_internal_paths():
    run, frame = sample()
    frame["capture_key"] = {"source_id": "industrial-camera", "session_id": "boot-2", "frame_id": "9007199254740993"}
    result = frame_view(run, frame)
    assert result["frame_key"] == frame["capture_key"]
    assert result["stream_session_id"] == "run-a"
    assert result["detections"][0]["confidence"] == 0
    assert result["detections"][0]["angle_deg"] == 0
    assert result["detections"][0]["center_px"] == [12, 7]
    assert result["capture_time"] is None
    run["error"] = "Permission denied C:/private/image.png"
    wire = json.dumps({"stream": stream_view(run), "frame": result})
    assert "C:/" not in wire and "internal-path" not in wire
    assert stream_view(run)["timings"]["mean_ms"] is None


def test_contract_hbb_square_and_invalid_values():
    _, frame = sample()
    detection = frame["detections"][0]
    assert detection_view(detection, "hbb")["orientation_valid"] is False
    detection["polygon"] = [[0, 0], [10, 0], [10, 10], [0, 10]]
    assert detection_view(detection)["angle_deg"] is None
    detection["polygon"][0][0] = float("nan")
    with pytest.raises(ValueError):
        detection_view(detection)
    detection["polygon"] = [[0, 0], [10, 10], [10, 0], [0, 10]]
    with pytest.raises(ValueError):
        detection_view(detection)


def test_preview_is_immutable_bounded_and_independent_of_database(tmp_path):
    source = tmp_path / "one.png"
    cv2.imwrite(str(source), np.full((32, 48, 3), 70, np.uint8))
    hub = Presentation()
    hub.CACHE_ITEMS = 2
    run, frame = sample()
    identities = []
    try:
        for index in range(3):
            frame["id"] = index + 1
            hub.update(run, frame, source)
            until(lambda: hub.snapshot()["frame"]["preview_status"] == "ready" and hub.snapshot()["frame"]["id"] == str(index+1))
            snapshot = hub.snapshot()
            identity = snapshot["frame"]["preview"]["id"]
            identities.append(identity)
            assert hub.preview(identity).startswith(b"\xff\xd8")
            snapshot["frame"]["width"] = -1
            assert hub.snapshot()["frame"]["width"] == 48
        assert hub.preview(identities[0]) is None
        assert hub.preview(identities[-1]) is not None
        assert len(hub.cache) == 2 and hub.cache_bytes <= hub.CACHE_BYTES
    finally:
        hub.close()


def test_old_preview_cannot_overwrite_new_session(tmp_path, monkeypatch):
    import backend.presentation as module
    source = tmp_path / "one.png"
    cv2.imwrite(str(source), np.zeros((32, 48, 3), np.uint8))
    started, release = threading.Event(), threading.Event()
    actual_decode = module.decode

    def delayed(data):
        started.set()
        assert release.wait(3)
        return actual_decode(data)

    monkeypatch.setattr(module, "decode", delayed)
    hub = Presentation()
    run, frame = sample()
    try:
        hub.update(run, frame, source)
        assert started.wait(2)
        next_run = {**run, "id": "run-b"}
        hub.update(next_run)
        release.set()
        until(lambda: hub.skipped == 1)
        assert hub.snapshot()["stream"]["session_id"] == "run-b"
        assert hub.snapshot()["frame"] is None
    finally:
        release.set()
        hub.close()


def test_fast_results_do_not_starve_slow_preview(tmp_path, monkeypatch):
    import backend.presentation as module
    source = tmp_path / "one.png"
    cv2.imwrite(str(source), np.zeros((32, 48, 3), np.uint8))
    actual_decode = module.decode
    entered, release = threading.Event(), threading.Event()
    calls = []

    def delayed(data):
        calls.append(1)
        if len(calls) == 1:
            entered.set()
            assert release.wait(3)
        else:
            time.sleep(.15)
        return actual_decode(data)

    monkeypatch.setattr(module, "decode", delayed)
    hub = Presentation()
    run, frame = sample()
    try:
        hub.update(run, frame, source)
        assert entered.wait(2)
        for number in range(2, 50):
            newer = {**frame, "id": number}
            hub.update(run, newer, source)
        release.set()
        until(lambda: hub.snapshot()["frame"]["preview_status"] == "ready")
        # Frame 1 must publish even though result 49 already exists; otherwise a
        # continuous fast source would starve the display indefinitely.
        assert hub.snapshot()["frame"]["id"] == "1"
        until(lambda: hub.snapshot()["frame"]["id"] == "49")
        assert hub.snapshot()["frame"]["preview_status"] == "ready"
        assert hub.skipped == 47
    finally:
        release.set()
        hub.close()


def test_subscribers_get_latest_without_unbounded_callback_or_queue():
    async def check():
        hub = Presentation()
        try:
            a, qa = hub.subscribe(asyncio.get_running_loop())
            b, qb = hub.subscribe(asyncio.get_running_loop())
            run, _ = sample()
            for i in range(100):
                run["processed"] = i
                hub.update(run)
            await asyncio.sleep(.01)
            assert qa.qsize() == qb.qsize() == 1
            assert (await qa.get())["stream"]["processed"] == 99
            assert (await qb.get())["stream"]["processed"] == 99
            hub.unsubscribe(a)
            hub.unsubscribe(b)
            assert not hub.subscribers
        finally:
            hub.close()
    asyncio.run(check())


class MemoryStore:
    def __init__(self, *_):
        self.runs = {}
        self.frames = {}
        self.block = False
        self.fail = False
        self.reads_forbidden = False
        self.entered, self.release = threading.Event(), threading.Event()

    def latest_run(self):
        assert not self.reads_forbidden
        return None

    def frame(self, run_id, frame_id):
        assert not self.reads_forbidden
        return self.frames.get((run_id, frame_id))

    def save_run(self, run):
        self.runs[run["id"]] = copy.deepcopy(run)

    def save_frame(self, run, frame, image_path):
        self.entered.set()
        if self.block:
            assert self.release.wait(4)
        if self.fail:
            raise OSError("simulated database failure")
        self.frames[(run["id"], frame["id"])] = {"data": copy.deepcopy(frame), "image_path": image_path}
        self.save_run(run)

    def ping(self):
        pass

    def close(self):
        pass


class Adapter:
    def __init__(self, *_):
        pass

    def load(self):
        return sample()[0]["model"]

    def predict(self, image, **parameters):
        return {"detections": copy.deepcopy(sample()[1]["detections"]),
                "timing_ms": {"preprocess": 0, "inference": 1, "postprocess": 0}}


def settings(tmp_path):
    source = tmp_path / "inputs"
    source.mkdir()
    cv2.imwrite(str(source / "one.png"), np.zeros((32, 48, 3), np.uint8))
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    return SimpleNamespace(runtime=runtime, weights=tmp_path / "fake.pt", database_url="unused",
                           sources={"test": {"id": "test", "label": "source", "path": source}}, defaults={})


PARAMS = {"source_id": "test", "engine": "pytorch", "confidence": .25, "iou": .45,
          "image_size": 640, "max_det": 100, "replay_fps": 10}


def test_status_and_stop_remain_responsive_during_db_write_and_intent_survives(tmp_path):
    store = MemoryStore()
    store.block = True
    runner = Runner(settings(tmp_path), store, Adapter)
    store.reads_forbidden = True
    try:
        run = runner.start(PARAMS)
        assert store.entered.wait(2)
        before = time.monotonic()
        snapshot = runner.snapshot()
        stopped = runner.control(run["id"], "stop")
        assert time.monotonic()-before < .2
        assert snapshot["frame"] is None
        assert stopped["status"] == "stopping"
        store.release.set()
        until(lambda: not runner.thread.is_alive())
        assert runner.snapshot()["run"]["status"] == "stopped"
        assert runner.snapshot()["run"]["processed"] == 1
        assert store.runs[run["id"]]["status"] == "stopped"
    finally:
        store.release.set()
        runner.close()


def test_database_commit_failure_does_not_publish_uncommitted_frame(tmp_path):
    store = MemoryStore()
    store.fail = True
    hub = Presentation()
    runner = Runner(settings(tmp_path), store, Adapter, hub)
    try:
        runner.start(PARAMS)
        until(lambda: not runner.thread.is_alive())
        assert runner.snapshot()["run"]["status"] == "failed"
        assert runner.snapshot()["frame"] is None
        assert hub.snapshot()["frame"] is None
        assert hub.snapshot()["stream"]["error"]["code"] == "RUN_FAILED"
    finally:
        runner.close()
        hub.close()


def test_empty_inbox_resume_is_persisted_without_waiting_for_a_frame(tmp_path):
    cfg = settings(tmp_path)
    cfg.sources["test"]["mode"] = "inbox"
    store = MemoryStore()
    runner = Runner(cfg, store, Adapter)
    try:
        run = runner.start(PARAMS)
        until(lambda: runner.snapshot()["run"]["status"] == "running")
        assert runner.snapshot()["run"]["total"] is None
        runner.control(run["id"], "pause")
        until(lambda: store.runs[run["id"]]["status"] == "paused")
        runner.control(run["id"], "resume")
        until(lambda: store.runs[run["id"]]["status"] == "running")
        assert runner.snapshot()["run"]["processed"] == 0
        runner.control(run["id"], "stop")
        until(lambda: not runner.thread.is_alive())
        assert store.runs[run["id"]]["status"] == "stopped"
    finally:
        runner.close()


def test_display_api_websocket_snapshot_readonly_and_missing_preview(tmp_path, monkeypatch):
    import backend.app as module
    monkeypatch.setattr(module, "Store", MemoryStore)
    with TestClient(module.create_app(settings(tmp_path), Adapter)) as client:
        assert client.get("/api/display/snapshot").json()["schema_version"] == "1.0"
        assert client.get("/api/display/previews/missing.jpg").status_code == 410
        with client.websocket_connect("/api/display/ws") as socket:
            assert socket.receive_json()["type"] == "snapshot"
            socket.send_json({"type": "pause"})
            assert socket.receive()["code"] == 1008
        with pytest.raises(Exception) as denied:
            with client.websocket_connect("/api/display/ws", headers={"Origin": "https://external.example"}):
                pass
        assert getattr(denied.value, "code", None) == 1008
