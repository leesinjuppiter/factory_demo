"""真实PostgreSQL隔离schema验证API生命周期；用确定性推理替身覆盖边界。

模型正确性由 test_inference.py 的真实权重测试与 scripts/smoke.py 负责。
"""
import io
import json
import os
import sys
import time
import uuid
from pathlib import Path

import cv2
import numpy as np
import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app import create_app
from backend.settings import Settings, TERMINAL
from backend.store import Store


class FakeAdapter:
    def __init__(self, weights):
        pass

    def load(self):
        return {"name": "deterministic-test-double", "classes": [{"id": 0, "name": "test", "label": "test", "color": "#008080"}],
                "box_type": "obb", "device": "cpu", "sha256": "test-only"}

    def predict(self, image, **kwargs):
        time.sleep(.02)
        return {"detections": [] if image.max() == 0 else [{"id": 1, "class_id": 0, "class_name": "test", "confidence": .9,
                  "polygon": [[5., 2.], [15., 5.], [12., 15.], [2., 12.]]}],
                "timing_ms": {"preprocess": 1., "inference": 20., "postprocess": 1.}}


@pytest.fixture
def context(tmp_path):
    # 所有schema由本测试唯一命名创建，仅清理本测试自己创建的对象。
    base = Settings()
    schema = "factory_test_" + uuid.uuid4().hex
    admin = psycopg.connect(base.database_url, autocommit=True)
    admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    directory = tmp_path / "inputs"
    directory.mkdir()
    for i in range(4):
        cv2.imwrite(str(directory / f"{i}.png"), np.full((32, 48, 3), i * 60, np.uint8))
    (directory / "broken.png").write_bytes(b"broken file")
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"weights": str(base.weights), "runtime_dir": str(tmp_path / "runtime"),
        "sources": [{"id": "test", "label": "API fixture", "path": str(directory)}], "defaults": base.defaults}), encoding="utf-8")
    # Settings要求postgres URL；options通过conninfo编码后直接赋值用于测试schema。
    cfg = Settings(config, base.database_url)
    cfg.database_url = make_conninfo(base.database_url, options=f"-c search_path={schema}")
    try:
        with TestClient(create_app(cfg, FakeAdapter)) as client:
            yield client, cfg, directory
    finally:
        assert schema.startswith("factory_test_") and len(schema) == 45
        admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
        admin.close()


def finish(client, run_id):
    until = time.monotonic() + 10
    while time.monotonic() < until:
        run = client.get(f"/api/runs/{run_id}").json()
        if run["status"] in TERMINAL:
            return run
        time.sleep(.03)
    raise AssertionError("test task did not terminate")


def start(client, **kwargs):
    result = client.post("/api/runs", json={"source_id": "test", "replay_fps": 10, **kwargs})
    assert result.status_code == 201, result.text
    return result.json()["id"]


def test_full_run_empty_and_bad_image_export_persistence(context):
    client, cfg, directory = context
    run_id = start(client)
    run = finish(client, run_id)
    assert (run["status"], run["total"], run["processed"], run["succeeded"], run["failed"]) == ("completed", 5, 5, 4, 1)
    assert run["detection_count"] == 3 and run["class_counts"] == {"0": 3}
    frames = client.get(f"/api/runs/{run_id}/frames").json()["items"]
    assert frames[0]["status"] == "ok" and frames[0]["detections"] == []
    assert frames[-1]["status"] == "error" and frames[-1]["error"]
    # 修改源图后历史图仍是原快照。
    (directory / "1.png").write_bytes(b"changed")
    image = client.get(frames[1]["image_url"])
    assert image.status_code == 200 and len(image.content) > 20
    assert client.get(frames[1]["annotated_url"]).headers["content-type"] == "image/png"
    exported = client.get(f"/api/runs/{run_id}/export").json()
    assert exported["run"]["processed"] == 5 and len(exported["frames"]) == 5
    csv = client.get(f"/api/runs/{run_id}/export?format=csv")
    assert "polygon_pixels" in csv.text and "broken.png" in csv.text
    assert client.get("/api/status").json()["run"]["id"] == run_id


def test_control_and_duplicate_start(context):
    client, _, _ = context
    run_id = start(client, replay_fps=1)
    assert client.post("/api/runs", json={"source_id": "test"}).status_code == 409
    for _ in range(100):
        if client.get(f"/api/runs/{run_id}").json()["status"] == "running":
            break
        time.sleep(.01)
    url = f"/api/runs/{run_id}/control"
    assert client.post(url, json={"action": "pause"}).status_code == 200
    time.sleep(.1)
    assert client.get(f"/api/runs/{run_id}").json()["status"] == "paused"
    assert client.post(url, json={"action": "pause"}).status_code == 200
    assert client.get(f"/api/runs/{run_id}/export").status_code == 409
    assert client.post(url, json={"action": "resume"}).status_code == 200
    assert client.post(url, json={"action": "stop"}).status_code == 200
    assert finish(client, run_id)["status"] == "stopped"
    assert client.post(url, json={"action": "stop"}).status_code == 200
    assert client.post(url, json={"action": "resume"}).status_code == 409
    next_id = start(client)
    assert next_id != run_id
    finish(client, next_id)


@pytest.mark.parametrize("data,code", [({"image_size": 641}, 422), ({"confidence": -1}, 422),
    ({"max_det": 1001}, 422), ({"replay_fps": 0}, 422), ({"engine": "openvino"}, 409),
    ({"engine": "tensorrt"}, 409), ({"source_id": "../../outside"}, 400), ({"source_path": "C:/"}, 422)])
def test_invalid_requests(context, data, code):
    client, _, _ = context
    response = client.post("/api/runs", json={"source_id": "test", **data})
    assert response.status_code == code and response.json()["detail"]["message"]


def test_upload_origin_missing_and_paging(context):
    client, _, _ = context
    data = cv2.imencode(".png", np.ones((20, 30, 3), dtype=np.uint8))[1].tobytes()
    response = client.post("/api/uploads", files={"file": ("中文图.png", data, "image/png")})
    assert response.status_code == 201
    run_id = start(client, source_id=response.json()["source_id"])
    assert finish(client, run_id)["total"] == 1
    assert client.post("/api/uploads", files={"file": ("invalid.png", b"notimage")}).status_code == 400
    assert client.post("/api/uploads", files={"file": ("bad.svg", b"<svg/>")}).status_code == 400
    assert client.post("/api/runs", json={"source_id": "test"}, headers={"Origin": "https://example.com"}).status_code == 403
    assert client.get("/api/runs?page_size=101").status_code == 422
    assert client.get("/api/runs/missing").status_code == 404
    assert client.get("/api/runs/missing/frames/1/image").status_code == 404


def test_chunked_upload_limit(context):
    client, _, _ = context
    def chunks():
        yield b'--boundary\r\nContent-Disposition: form-data; name="file"; filename="large.png"\r\nContent-Type: image/png\r\n\r\n'
        for _ in range(22):
            yield b"x" * 1024 * 1024
        yield b"\r\n--boundary--\r\n"
    response = client.post("/api/uploads", content=chunks(), headers={"Content-Type": "multipart/form-data; boundary=boundary"})
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "UPLOAD_TOO_LARGE"


def test_changed_file_and_empty_source(context):
    client, _, directory = context
    run_id = start(client, replay_fps=1)
    (directory / "3.png").write_bytes(b"changed-after-snapshot")
    run = finish(client, run_id)
    assert run["failed"] == 2
    for path in directory.iterdir():
        path.unlink()  # 仅pytest刚创建的输入夹具。
    assert client.post("/api/runs", json={"source_id": "test"}).status_code == 400


def test_single_instance_lock(context):
    _, cfg, _ = context
    with pytest.raises(RuntimeError, match="单进程"):
        Store(cfg.database_url)


def test_recovery_of_interrupted_run(context):
    client, cfg, _ = context
    run_id = start(client)
    finish(client, run_id)
    store = client.app.state.store
    record = store.get_run(run_id)
    record["status"] = "running"
    store.save_run(record)
    store.close()
    new_store = Store(cfg.database_url)
    try:
        assert new_store.get_run(run_id)["status"] == "interrupted"
        assert new_store.get_run(run_id)["processed"] == 5
    finally:
        client.app.state.store = new_store
        client.app.state.runner.store = new_store
