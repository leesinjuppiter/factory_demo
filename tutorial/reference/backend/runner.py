"""单活动任务。控制命令在帧边界生效，结果先提交数据库再供前端读取。"""
import copy
import hashlib
import json
import logging
import os
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .images import InputError, check_space, decode, inventory
from .settings import TERMINAL

LOG = logging.getLogger("factory_demo")


def now():
    return datetime.now(timezone.utc).isoformat()


class Conflict(ValueError):
    pass


class Runner:
    def __init__(self, settings, store, adapter_factory=None, presentation=None):
        self.settings, self.store = settings, store
        self.condition = threading.Condition(threading.RLock())
        self.thread = None
        self.current = None
        self.shutting_down = False
        self.adapter = None
        self.adapter_factory = adapter_factory
        self.presentation = presentation
        self._starting = False
        self._control_dirty = False
        self.latest_frame = None
        self.model = {"name": settings.weights.stem, "path": str(settings.weights), "sha256": None,
                      "classes": [], "box_type": "obb", "device": os.getenv("FACTORY_DEVICE", "cpu")}
        # Recovery is a startup operation. Steady-state status/display reads never
        # query PostgreSQL; cold start still intentionally requires the database.
        self.current = store.latest_run()
        recovered_path = None
        if self.current and self.current.get("latest_frame_id") is not None:
            row = store.frame(self.current["id"], self.current["latest_frame_id"])
            if row:
                self.latest_frame = row["data"]
                recovered_path = Path(row["image_path"]) if row["image_path"] else None
        if self.presentation:
            self.presentation.update(self.current, self.latest_frame, recovered_path)

    def _publish(self, frame=None, image_path=None):
        """Called with the short state lock held; never performs image I/O."""
        if self.presentation:
            self.presentation.update(self.current, frame, image_path)

    def source(self, source_id):
        if source_id in self.settings.sources:
            src = self.settings.sources[source_id]
            if src.get("mode") == "inbox":
                if not src["path"].is_dir():
                    raise InputError("相机接收目录不存在，请先运行模拟拍照脚本")
                receipt = self.settings.runtime / "receipts" / (hashlib.sha256(source_id.encode()).hexdigest() + ".sqlite")
                return src["label"], {"inbox_root": src["path"], "receipt_path": receipt}
            return src["label"], inventory(src["path"])
        if source_id.startswith("upload_"):
            try:
                uid = str(uuid.UUID(source_id[7:]))
                record = self.settings.runtime / "uploads" / uid / "source.json"
                meta = json.loads(record.read_text(encoding="utf-8"))
                files = inventory(record.parent)
                for item in files:
                    item["name"] = meta["name"]
                return meta["name"], files
            except (ValueError, OSError):
                raise InputError("上传图片不存在，请重新上传") from None
        raise InputError("未知数据源，请选择已配置目录或上传单图")

    def start(self, params):
        with self.condition:
            if self.shutting_down or self._starting or (self.current and self.current["status"] not in TERMINAL):
                raise Conflict("已有活动任务，请等待结束或先停止")
            self._starting = True
        files = None
        try:
            label, files = self.source(params["source_id"])
            continuous = isinstance(files, dict) and "inbox_root" in files
            if not continuous and not files:
                raise InputError("所选目录没有支持的图片")
            check_space(self.settings.runtime)
            run = {"id": str(uuid.uuid4()), "status": "loading", "source_id": params["source_id"],
                   "source_label": label, "created_at": now(), "started_at": None, "finished_at": None,
                   "total": None if continuous else len(files), "processed": 0, "succeeded": 0, "failed": 0,
                   "detection_count": 0, "class_counts": {}, "config": params, "model": copy.deepcopy(self.model),
                   "timings": {"mean_ms": None, "p50_ms": None, "p95_ms": None, "fps": None},
                   "error": None, "latest_frame_id": None}
            self.store.save_run(run)
            with self.condition:
                self.current, self.latest_frame = run, None
                self._control_dirty = False
                if self.shutting_down:
                    run["status"] = "stopping"
                self._publish()
                self.thread = threading.Thread(target=self._work, args=(files,), name="factory-inference", daemon=True)
                self.thread.start()
                return copy.deepcopy(run)
        except Exception:
            if hasattr(files, "close"):
                files.close()
            raise
        finally:
            with self.condition:
                self._starting = False

    def control(self, run_id, action):
        with self.condition:
            run = self.current
            if not run or run["id"] != run_id:
                raise Conflict("只能控制当前活动任务")
            status = run["status"]
            if action == "stop" and status in {"stopping", "stopped"}:
                return copy.deepcopy(run)
            if status in TERMINAL:
                raise Conflict("任务已结束；请创建新任务重新运行")
            if action == "pause":
                if status not in {"running", "pausing", "paused"}:
                    raise Conflict("仅运行中的任务可以暂停")
                if status == "running":
                    run["status"] = "pausing"
            elif action == "resume":
                if status not in {"running", "paused", "pausing"}:
                    raise Conflict("当前状态不可继续")
                run["status"] = "running"
            else:
                run["status"] = "stopping"
            # Accept an in-memory intent. The single worker persists transitions
            # at a frame boundary; a slow database cannot hold the state lock.
            self._control_dirty = True
            self._publish()
            self.condition.notify_all()
            return copy.deepcopy(run)

    def snapshot(self):
        with self.condition:
            return {"run": copy.deepcopy(self.current), "frame": copy.deepcopy(self.latest_frame)}

    def _boundary(self):
        while True:
            transition = None
            with self.condition:
                if self.current["status"] == "pausing":
                    self.current["status"] = "paused"
                    self._publish()
                if self.current["status"] == "stopping":
                    return False
                if self._control_dirty:
                    transition = copy.deepcopy(self.current)
                    self._control_dirty = False
                if transition is None and self.current["status"] != "paused":
                    return True
            if transition is not None:
                self.store.save_run(transition)
            with self.condition:
                if self.current["status"] == "paused" and not self._control_dirty:
                    self.condition.wait()

    def _work(self, files):
        run = self.current
        continuous = isinstance(files, dict) and "inbox_root" in files
        times = deque(maxlen=1000) if continuous else []
        total_time = success_count = 0
        try:
            if continuous:
                from .acquisition import InboxSource
                files = InboxSource(files["inbox_root"], files["receipt_path"])
            if self.adapter is None:
                if self.adapter_factory is None:
                    from .inference.factory import create_adapter
                    adapter = create_adapter(run["config"]["engine"], self.settings.weights)
                else:
                    adapter = self.adapter_factory(self.settings.weights)
                model = adapter.load()
                self.adapter, self.model = adapter, model
            with self.condition:
                run["model"] = copy.deepcopy(self.model)
                if run["status"] != "stopping":
                    run.update(status="running", started_at=now())
                initial = copy.deepcopy(run)
                self._publish()
            self.store.save_run(initial)
            output = self.settings.runtime / "runs" / run["id"] / "images"
            output.mkdir(parents=True, exist_ok=True)
            index = 0
            while True:
                if not self._boundary():
                    break
                if continuous:
                    item = files.next_item()
                    if item is None:
                        with self.condition:
                            if run["status"] == "running":
                                self.condition.wait(timeout=.1)
                        continue
                else:
                    if index >= len(files):
                        break
                    item = files[index]
                index += 1
                check_space(self.settings.runtime)
                tick = time.perf_counter()
                frame, image_path = self._frame(run, index, item, output)
                with self.condition:
                    # 保存失败不继续处理：否则累计统计可能与数据库脱节。
                    updated = copy.deepcopy(run)
                    updated["processed"] += 1
                    updated["latest_frame_id"] = index
                    updated["succeeded" if frame["status"] == "ok" else "failed"] += 1
                    for det in frame["detections"]:
                        key = str(det["class_id"])
                        updated["class_counts"][key] = updated["class_counts"].get(key, 0) + 1
                    updated["detection_count"] += len(frame["detections"])
                    if frame["status"] == "ok":
                        times.append(frame["timing_ms"]["total"])
                        total_time += frame["timing_ms"]["total"]
                        success_count += 1
                        mean = total_time / success_count
                        updated["timings"] = {"mean_ms": mean, "p50_ms": float(np.percentile(times, 50)),
                                              "p95_ms": float(np.percentile(times, 95)), "fps": 1000 / mean if mean else 0}
                        if continuous:
                            updated["timings"]["quantile_window"] = len(times)
                # One worker owns persisted state. Control can change its intent
                # during this transaction; never overwrite that intent afterwards.
                self.store.save_frame(updated, frame, image_path)
                with self.condition:
                    for key, value in updated.items():
                        if key not in {"status", "error", "finished_at"}:
                            run[key] = value
                    self.latest_frame = copy.deepcopy(frame)
                    self._publish(frame, image_path)
                if continuous:
                    files.ack(item)
                with self.condition:
                    if not continuous and index < len(files):
                        remaining = 1 / run["config"]["replay_fps"] - (time.perf_counter() - tick)
                        if remaining > 0 and run["status"] == "running":
                            self.condition.wait(timeout=remaining)
            with self.condition:
                run.update(status="stopped" if run["status"] == "stopping" else "completed", finished_at=now())
                final = copy.deepcopy(run)
            self.store.save_run(final)
            with self.condition:
                self._publish()
        except Exception as exc:
            LOG.exception("运行 %s 失败", run["id"])
            with self.condition:
                run.update(status="failed", error=f"{type(exc).__name__}: {exc}", finished_at=now())
                failed = copy.deepcopy(run)
                self._publish()
            try:
                self.store.save_run(failed)
            except Exception:
                LOG.exception("数据库不可用，失败状态保留在内存；下次启动标记 interrupted")
        finally:
            if continuous and hasattr(files, "close"):
                files.close()

    def _frame(self, run, index, item, output):
        path = item["path"]
        base = f"/api/runs/{run['id']}/frames/{index}"
        frame = {"id": index, "run_id": run["id"], "name": item.get("name", path.name),
                 "width": 0, "height": 0, "image_url": None, "annotated_url": None,
                 "status": "error", "error": None, "detections": [], "timing_ms": {}, "created_at": now()}
        for key in ("capture_key", "capture_time", "capture_clock_domain", "published_at"):
            if key in item:
                frame[key] = copy.deepcopy(item[key])
        saved = None
        try:
            tick = time.perf_counter()
            stat = path.stat()
            if stat.st_size != item["size"] or stat.st_mtime_ns != item["mtime"]:
                raise InputError("图片在创建任务后发生变化，请重新创建任务")
            from .settings import LIMITS
            with path.open("rb") as stream:
                data = stream.read(LIMITS["max_file_bytes"] + 1)
            after = path.stat()
            if (after.st_size, after.st_mtime_ns) != (item["size"], item["mtime"]):
                raise InputError("图片在读取时发生变化，请重新创建任务")
            digest = hashlib.sha256(data).hexdigest()
            if item.get("expected_sha256") and digest != item["expected_sha256"]:
                raise InputError("相机图片内容与发布清单哈希不一致")
            image = decode(data)
            read_ms = (time.perf_counter() - tick) * 1000
            # 原始字节固化，历史查看和导出始终使用该次推理的输入。
            saved = output / f"{index:06d}{path.suffix.lower()}"
            saved.write_bytes(data)
            frame.update(width=int(image.shape[1]), height=int(image.shape[0]), image_url=base + "/image",
                         annotated_url=base + "/annotated", sha256=digest)
        except (OSError, InputError) as exc:
            frame["error"] = str(exc)
            return frame, saved
        params = run["config"]
        result = self.adapter.predict(image, image_size=params["image_size"], confidence=params["confidence"],
                                      iou=params["iou"], max_det=params["max_det"])
        from .contracts import detection_view
        for item in result["detections"]:
            geometry = detection_view(item, self.model.get("box_type", "obb"))
            item.update({key: geometry[key] for key in ("center_px", "angle_deg", "angle_convention", "orientation_valid", "geometry_type")})
        timing = {"read": read_ms, **result["timing_ms"]}
        timing["total"] = sum(timing[k] for k in ("read", "preprocess", "inference", "postprocess"))
        frame.update(status="ok", detections=result["detections"], timing_ms=timing)
        return frame, saved

    def close(self):
        with self.condition:
            self.shutting_down = True
            if self.current and self.current["status"] not in TERMINAL:
                self.current["status"] = "stopping"
                self.condition.notify_all()
        if self.thread:
            self.thread.join(timeout=30)
        return not self.thread or not self.thread.is_alive()
