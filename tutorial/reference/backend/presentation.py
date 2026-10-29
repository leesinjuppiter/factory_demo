"""Bounded preview worker and independent event-driven display subscribers."""
import asyncio
import copy
import logging
import threading
import time
import uuid
from collections import OrderedDict

import cv2

from .contracts import SCHEMA_VERSION, frame_view, stream_view
from .images import decode
from . import profiling

LOG = logging.getLogger("factory_demo.presentation")


class Presentation:
    CACHE_BYTES = 32 * 1024 * 1024
    CACHE_ITEMS = 32
    MAX_SUBSCRIBERS = 16
    PREVIEW_WIDTH = 1024

    def __init__(self):
        self.condition = threading.Condition(threading.RLock())
        self.stream = self.frame = self.pending = None
        self.revision = 0
        self.cache = OrderedDict()
        self.cache_bytes = 0
        self.subscribers = {}
        self.skipped = self.errors = 0
        self.result_sequence = self.display_sequence = 0
        self.latest_result_key = None
        self.pending_queued_ns = 0
        self.closed = False
        self.worker = threading.Thread(target=self._work, name="factory-preview", daemon=True)
        self.worker.start()

    def _snapshot(self):
        return {"schema_version": SCHEMA_VERSION, "type": "snapshot", "revision": self.revision,
                "stream": copy.deepcopy(self.stream), "frame": copy.deepcopy(self.frame),
                "service": {"preview_skipped": self.skipped, "preview_errors": self.errors,
                            "preview_cache_bytes": self.cache_bytes, "preview_cache_limit_bytes": self.CACHE_BYTES,
                            "subscribers": len(self.subscribers), "latest_result_key": copy.deepcopy(self.latest_result_key)}}

    def snapshot(self):
        with self.condition:
            return self._snapshot()

    def _changed(self):
        self.revision += 1
        for token, sub in list(self.subscribers.items()):
            if not sub["scheduled"]:
                sub["scheduled"] = True
                try:
                    sub["loop"].call_soon_threadsafe(self._deliver, token)
                except RuntimeError:
                    self.subscribers.pop(token, None)

    def _deliver(self, token):
        started = time.perf_counter_ns()
        with self.condition:
            sub = self.subscribers.get(token)
            if not sub:
                return
            sub["scheduled"] = False
            snapshot = self._snapshot()
            copied = time.perf_counter_ns()
            queue = sub["queue"]
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(snapshot)
        frame = snapshot.get("frame") or {}
        profiling.record("ws_queue", run_id=frame.get("stream_session_id"), frame_id=frame.get("id"),
                         subscriber=token, revision=snapshot["revision"],
                         lock_and_snapshot_ms=(copied-started)/1e6,
                         queue_ms=(time.perf_counter_ns()-copied)/1e6)

    def subscribe(self, loop):
        with self.condition:
            if len(self.subscribers) >= self.MAX_SUBSCRIBERS or self.closed:
                raise RuntimeError("展示订阅已达上限或服务正在关闭")
            token, queue = uuid.uuid4().hex, asyncio.Queue(maxsize=1)
            self.subscribers[token] = {"loop": loop, "queue": queue, "scheduled": False}
            queue.put_nowait(self._snapshot())
            return token, queue

    def unsubscribe(self, token):
        with self.condition:
            self.subscribers.pop(token, None)

    def update(self, run, frame=None, image_path=None):
        stream = stream_view(run)
        projected = frame_view(run, frame) if run and frame else None
        with self.condition:
            previous_session = self.stream.get("session_id") if self.stream else None
            self.stream = stream
            if stream is None or stream["session_id"] != previous_session:
                self.frame = None
                self.latest_result_key = None
                self.result_sequence = self.display_sequence = 0
                if self.pending is not None:
                    self.skipped += 1
                    self.pending = None
            if projected is not None:
                self.result_sequence += 1
                self.latest_result_key = projected["frame_key"]
                if projected["status"] == "ok" and image_path is not None:
                    if self.pending is not None:
                        self.skipped += 1
                    self.pending = (projected, self.result_sequence, stream["model"]["version"], image_path)
                    self.pending_queued_ns = time.perf_counter_ns()
                    # Keep the latest COMPLETE display frame while newer results
                    # arrive. Faster inference must not cancel every slow encode.
                    if self.frame is None or self.frame["preview_status"] != "ready":
                        self.frame = projected
                    self.condition.notify()
                else:
                    self.frame = projected
                    self.display_sequence = self.result_sequence
                    if self.pending is not None:
                        self.skipped += 1
                        self.pending = None
            self._changed()

    def preview(self, identity):
        with self.condition:
            return self.cache.get(identity)

    def _work(self):
        while True:
            with self.condition:
                while self.pending is None and not self.closed:
                    self.condition.wait()
                if self.closed:
                    return
                projected, sequence, model_version, path = self.pending
                queued_ns = self.pending_queued_ns
                dequeued_ns = time.perf_counter_ns()
                key, session = projected["frame_key"], projected["stream_session_id"]
                self.pending = None
            try:
                data = path.read_bytes()
                read_done = time.perf_counter_ns()
                image = decode(data)
                decode_done = time.perf_counter_ns()
                height, width = image.shape[:2]
                scale = min(1, self.PREVIEW_WIDTH / width)
                size = (max(1, round(width*scale)), max(1, round(height*scale)))
                resized = cv2.resize(image, size, interpolation=cv2.INTER_AREA) if size != (width, height) else image
                resize_done = time.perf_counter_ns()
                ok, encoded = cv2.imencode(".jpg", resized, [cv2.IMWRITE_JPEG_QUALITY, 82])
                encode_done = time.perf_counter_ns()
                if not ok:
                    raise ValueError("JPEG 编码失败")
                data = encoded.tobytes()
                if len(data) > self.CACHE_BYTES:
                    raise ValueError("预览超过缓存字节上限")
                identity = uuid.uuid4().hex
                preview = {"id": identity, "url": f"/api/display/previews/{identity}.jpg", "mime": "image/jpeg",
                           "width": size[0], "height": size[1], "sx": size[0]/width, "sy": size[1]/height, "ox": 0, "oy": 0}
                cache_start = time.perf_counter_ns()
                with self.condition:
                    if (not self.stream or self.stream["session_id"] != session
                            or self.stream["model"]["version"] != model_version or sequence <= self.display_sequence):
                        self.skipped += 1
                        continue
                    while self.cache and (len(self.cache) >= self.CACHE_ITEMS or self.cache_bytes+len(data) > self.CACHE_BYTES):
                        _, old = self.cache.popitem(last=False)
                        self.cache_bytes -= len(old)
                    self.cache[identity] = data
                    self.cache_bytes += len(data)
                    self.frame = projected
                    self.display_sequence = sequence
                    self.frame.update(preview=preview, preview_status="ready")
                    self._changed()
                ready_ns = time.perf_counter_ns()
                profiling.record("preview", run_id=session, frame_id=projected["id"],
                                 preview_id=identity, queued_ns=queued_ns, ready_ns=ready_ns,
                                 queue_wait_ms=(dequeued_ns-queued_ns)/1e6,
                                 snapshot_read_ms=(read_done-dequeued_ns)/1e6,
                                 decode_ms=(decode_done-read_done)/1e6,
                                 resize_ms=(resize_done-decode_done)/1e6,
                                 jpeg_encode_ms=(encode_done-resize_done)/1e6,
                                 pack_bytes_ms=(cache_start-encode_done)/1e6,
                                 cache_publish_ms=(ready_ns-cache_start)/1e6,
                                 preview_work_ms=(ready_ns-dequeued_ns)/1e6, bytes=len(data))
            except Exception:
                LOG.exception("预览生成失败（检测及归档结果不受影响）")
                with self.condition:
                    self.errors += 1
                    if self.stream and self.stream["session_id"] == session and sequence > self.display_sequence:
                        # A newer successful preview, when available, must remain
                        # intact; otherwise expose the failed frame explicitly.
                        if not self.frame or self.frame["preview_status"] != "ready":
                            self.frame = projected
                            self.frame.update(preview=None, preview_status="error")
                        self._changed()

    def close(self):
        with self.condition:
            self.closed = True
            self.pending = None
            self.condition.notify_all()
        self.worker.join(timeout=10)
