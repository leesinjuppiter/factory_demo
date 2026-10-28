"""只使用tmp_path的文件发布/消费边界测试，不启动相机或数据库服务。"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.acquisition import InboxSource
from backend.images import InputError

spec = importlib.util.spec_from_file_location("camera_sim", ROOT / "scripts/simulate_camera.py")
sim = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sim)


def create(tmp_path):
    root = tmp_path / "inbox"
    root.mkdir()
    return root, tmp_path / "receipts.sqlite"


def test_only_published_frames_and_receipts_survive_restart(tmp_path):
    root, receipt = create(tmp_path)
    (root / "unfinished.jpg.part").write_bytes(b"unfinished")
    (root / "not_announced.jpg").write_bytes(b"completed but not published")
    source = InboxSource(root, receipt)
    assert source.next_item() is None
    ready = sim.publish(root, b"fixture", ".jpg", "camera", "session", 1)
    source.last_scan = 0
    item = source.next_item()
    assert item["capture_key"] == {"source_id": "camera", "session_id": "session", "frame_id": "1"}
    assert item["capture_time"] is None
    source.ack(item)
    source.close()
    source = InboxSource(root, receipt)
    try:
        assert source.next_item() is None
        assert ready.exists() and item["path"].read_bytes() == b"fixture"
    finally:
        source.close()


@pytest.mark.parametrize("change", ["size", "path", "digest", "timezone", "schema"])
def test_invalid_manifest_is_explicit_error(tmp_path, change):
    root, receipt = create(tmp_path)
    ready = sim.publish(root, b"fixture", ".jpg", "camera", "session", 1)
    meta = json.loads(ready.read_text())
    if change == "size": meta["size"] = 99
    if change == "path": meta["image"] = "../outside.jpg"
    if change == "digest": meta["sha256"] = "not-a-digest"
    if change == "timezone": meta["published_at"] = "2026-10-28T10:00:00"
    if change == "schema": meta["schema_version"] = "9.0"
    ready.write_text(json.dumps(meta))
    source = InboxSource(root, receipt)
    try:
        with pytest.raises(InputError): source.next_item()
    finally: source.close()


def test_unacknowledged_frame_is_reoffered_after_restart(tmp_path):
    root, receipt = create(tmp_path)
    sim.publish(root, b"fixture", ".jpg", "camera", "session", 1)
    source = InboxSource(root, receipt)
    first = source.next_item()
    source.close()
    source = InboxSource(root, receipt)
    try: assert source.next_item()["capture_key"] == first["capture_key"]
    finally: source.close()


def test_reused_identity_or_modified_receipt_is_rejected(tmp_path):
    root, receipt = create(tmp_path)
    sim.publish(root, b"fixture", ".jpg", "camera", "session", 1)
    source = InboxSource(root, receipt)
    source.ack(source.next_item())
    sim.publish(root, b"fixture", ".jpg", "camera", "session", 1)
    source.last_scan = 0
    try:
        with pytest.raises(InputError): source.next_item()
    finally: source.close()


def test_pending_capacity_fails_without_removing_images(tmp_path, monkeypatch):
    root, receipt = create(tmp_path)
    for index in range(3): sim.publish(root, b"fixture", ".jpg", "camera", "session", index)
    monkeypatch.setitem(sys.modules['backend.acquisition'].LIMITS, 'max_images', 2)
    source = InboxSource(root, receipt)
    try:
        with pytest.raises(InputError): source.next_item()
        assert len(list(root.glob('*.jpg'))) == 3
    finally: source.close()
