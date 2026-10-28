"""Factory Demo 的同源 HTTP API；生产前端由此服务托管。"""
import csv
import io
import json
import logging
import uuid
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import cv2
import numpy as np
import psycopg
from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .images import InputError, check_space, decode, inventory
from .runner import Conflict, Runner
from .settings import EXTENSIONS, LIMITS, ROOT, TERMINAL, Settings
from .store import Store
from .presentation import Presentation
from .inference.factory import capabilities as engine_capabilities

LOG = logging.getLogger("factory_demo")


def fail(status, code, message):
    raise HTTPException(status, detail={"code": code, "message": message})


class UploadSizeLimit:
    """在multipart解析之前限制实际请求字节，包括无Content-Length的分块上传。"""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] != "/api/uploads":
            await self.app(scope, receive, send)
            return
        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            received += len(message.get("body", b""))
            if received > LIMITS["max_file_bytes"] + 1024 * 1024:
                fail(413, "UPLOAD_TOO_LARGE", "上传请求超过21 MiB（图片本身最多20 MiB）")
            return message
        await self.app(scope, limited_receive, send)


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    source_id: str = Field(min_length=1, max_length=100)
    engine: Literal["pytorch", "openvino", "tensorrt"] = "pytorch"
    confidence: float = Field(default=0.25, ge=0.001, le=1)
    iou: float = Field(default=0.45, ge=0.01, le=1)
    image_size: int = Field(default=640, ge=320, le=1280)
    max_det: int = Field(default=300, ge=1, le=1000)
    replay_fps: float = Field(default=1, ge=0.1, le=10)

    @field_validator("image_size")
    @classmethod
    def stride(cls, value):
        if value % 32:
            raise ValueError("image_size 必须是 32 的整数倍")
        return value


class ControlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["pause", "resume", "stop"]


def create_app(settings=None, adapter_factory=None):
    @asynccontextmanager
    async def lifespan(app):
        cfg = settings or Settings()
        store = Store(cfg.database_url)
        app.state.settings = cfg
        app.state.store = store
        app.state.presentation = Presentation()
        try:
            app.state.runner = Runner(cfg, store, adapter_factory, app.state.presentation)
            yield
        finally:
            # Cold startup still requires PostgreSQL; only runtime reads decouple.
            runner = getattr(app.state, "runner", None)
            if runner is None or runner.close():
                store.close()
            app.state.presentation.close()

    app = FastAPI(title="Factory Demo", version="1.3.0", lifespan=lifespan)
    app.add_middleware(UploadSizeLimit)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])

    @app.middleware("http")
    async def local_origin(request, call_next):
        # 本机无登录版本，限制浏览器跨站写请求；不会开放CORS。
        origin = request.headers.get("origin")
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and origin:
            parsed = urlsplit(origin)
            if parsed.hostname not in {"127.0.0.1", "localhost"}:
                return JSONResponse({"detail": {"code": "ORIGIN_DENIED", "message": "仅允许本机页面操作"}}, status_code=403)
        length = request.headers.get("content-length")
        if request.url.path == "/api/uploads" and length:
            try:
                oversized = int(length) > LIMITS["max_file_bytes"] + 1024 * 1024
            except ValueError:
                oversized = True
            if oversized:
                return JSONResponse({"detail": {"code": "UPLOAD_TOO_LARGE", "message": "上传超过20 MiB限制"}}, status_code=413)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        if request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        message = "; ".join(".".join(str(v) for v in e["loc"]) + ": " + e["msg"] for e in exc.errors())
        return JSONResponse({"detail": {"code": "INVALID_REQUEST", "message": message}}, status_code=422)

    @app.exception_handler(InputError)
    async def input_error(request, exc):
        return JSONResponse({"detail": {"code": "INVALID_INPUT", "message": str(exc)}}, status_code=400)

    @app.exception_handler(Conflict)
    async def conflict_error(request, exc):
        return JSONResponse({"detail": {"code": "RUN_CONFLICT", "message": str(exc)}}, status_code=409)

    @app.exception_handler(psycopg.Error)
    async def db_error(request, exc):
        LOG.error("PostgreSQL operation failed: %s", type(exc).__name__)
        return JSONResponse({"detail": {"code": "DATABASE_UNAVAILABLE", "message": "数据库连接异常，请检查本机 PostgreSQL 并重启服务"}}, status_code=503)

    @app.exception_handler(OSError)
    async def filesystem_error(request, exc):
        LOG.error("Filesystem operation failed: %s", type(exc).__name__)
        return JSONResponse({"detail": {"code": "FILESYSTEM_ERROR", "message": "文件不可访问或存储失败，请检查目录权限和剩余空间"}}, status_code=500)

    def get_run(run_id):
        run = app.state.store.get_run(run_id)
        if not run:
            fail(404, "RUN_NOT_FOUND", "运行记录不存在")
        return run

    def get_frame(run_id, frame_id):
        row = app.state.store.frame(run_id, frame_id)
        if not row:
            fail(404, "FRAME_NOT_FOUND", "图片记录不存在")
        return row

    def frame_path(row):
        path = Path(row["image_path"]).resolve() if row["image_path"] else None
        runtime = app.state.settings.runtime
        if not path or not path.is_relative_to(runtime) or not path.is_file():
            fail(404, "IMAGE_MISSING", "图片快照不可用，记录仍然保留")
        return path

    @app.get("/api/health")
    def health():
        app.state.store.ping()
        run = app.state.runner.current
        return {"status": "ok", "database": "postgresql", "active_run_id": run["id"] if run and run["status"] not in TERMINAL else None}

    @app.get("/api/capabilities")
    def capabilities():
        cfg = app.state.settings
        sources = []
        for source in cfg.sources.values():
            try:
                count = None if source.get("mode") == "inbox" else len(inventory(source["path"]))
                error = None if source["path"].is_dir() else "目录尚不存在，请先启动模拟拍照脚本"
            except (InputError, OSError) as exc:
                count, error = 0, str(exc)
            sources.append({"id": source["id"], "label": source["label"], "count": count, "error": error,
                            "mode": "continuous" if source.get("mode") == "inbox" else "finite"})
        return {"protocol_version": "1.0", "engines": engine_capabilities(cfg.weights),
            "model": app.state.runner.model, "limits": LIMITS, "sources": sources, "defaults": cfg.defaults}

    @app.post("/api/uploads", status_code=201)
    async def upload(file: UploadFile = File(...)):
        cfg = app.state.settings
        name = Path((file.filename or "image").replace("\\", "/")).name
        ext = Path(name).suffix.lower()
        try:
            if ext not in EXTENSIONS or len(name) > 180:
                raise InputError("仅支持文件名不超过180字符的 JPG/JPEG/PNG/BMP")
            data = await file.read(LIMITS["max_file_bytes"] + 1)
            # 解码检查移到线程，避免大图阻塞异步HTTP循环。
            from starlette.concurrency import run_in_threadpool
            await run_in_threadpool(decode, data)
            check_space(cfg.runtime)
            uid = str(uuid.uuid4())
            folder = cfg.runtime / "uploads" / uid
            folder.mkdir(parents=True)
            try:
                (folder / ("image" + ext)).write_bytes(data)
                (folder / "source.json").write_text(json.dumps({"name": name}, ensure_ascii=False), encoding="utf-8")
            except OSError:
                # 仅移除本请求刚创建的两个文件，不递归清理其他运行的数据。
                (folder / ("image" + ext)).unlink(missing_ok=True)
                (folder / "source.json").unlink(missing_ok=True)
                folder.rmdir()
                raise
            return {"source_id": "upload_" + uid, "label": name, "count": 1}
        finally:
            await file.close()

    @app.post("/api/runs", status_code=201)
    def start(params: RunRequest):
        if params.engine != "pytorch":
            fail(409, "ENGINE_UNAVAILABLE", "此引擎本版未实现，请选择 PyTorch")
        return app.state.runner.start(params.model_dump())

    @app.get("/api/status")
    def status():
        return app.state.runner.snapshot()

    @app.get("/api/display/snapshot")
    def display_snapshot():
        return app.state.presentation.snapshot()

    @app.get("/api/display/previews/{identity}.jpg")
    def preview(identity: str):
        data = app.state.presentation.preview(identity)
        if data is None:
            fail(410, "PREVIEW_EXPIRED", "预览已过期，请获取最新展示快照")
        return Response(data, media_type="image/jpeg")

    @app.websocket("/api/display/ws")
    async def display_socket(websocket: WebSocket):
        origin = websocket.headers.get("origin")
        if origin and urlsplit(origin).hostname not in {"localhost", "127.0.0.1", "testserver"}:
            await websocket.close(code=1008, reason="只允许本机展示连接")
            return
        try:
            token, queue = app.state.presentation.subscribe(asyncio.get_running_loop())
        except RuntimeError:
            await websocket.close(code=1013)
            return
        try:
            await websocket.accept()
        except Exception:
            app.state.presentation.unsubscribe(token)
            raise

        async def send():
            while True:
                try:
                    packet = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    packet = {"schema_version": "1.0", "type": "heartbeat",
                              "revision": app.state.presentation.snapshot()["revision"]}
                await asyncio.wait_for(websocket.send_json(packet), timeout=5)

        async def receive():
            # The display channel has no production control capability.
            message = await websocket.receive()
            if message["type"] != "websocket.disconnect":
                await websocket.close(code=1008, reason="展示通道只读")

        tasks = [asyncio.create_task(send()), asyncio.create_task(receive())]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        except WebSocketDisconnect:
            pass
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            app.state.presentation.unsubscribe(token)
            try:
                await websocket.close()
            except (RuntimeError, WebSocketDisconnect):
                pass

    @app.get("/api/runs")
    def runs(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
        return app.state.store.runs(page, page_size)

    @app.get("/api/runs/{run_id}")
    def run(run_id: str):
        return get_run(run_id)

    @app.post("/api/runs/{run_id}/control")
    def control(run_id: str, params: ControlRequest):
        current = app.state.runner.snapshot()["run"]
        if not current or current["id"] != run_id:
            get_run(run_id)
        return app.state.runner.control(run_id, params.action)

    @app.get("/api/runs/{run_id}/frames")
    def frames(run_id: str, page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100)):
        get_run(run_id)
        return app.state.store.frames(run_id, page, page_size)

    @app.get("/api/runs/{run_id}/frames/{frame_id}")
    def frame(run_id: str, frame_id: int):
        return get_frame(run_id, frame_id)["data"]

    @app.get("/api/runs/{run_id}/frames/{frame_id}/image")
    def image(run_id: str, frame_id: int):
        return FileResponse(frame_path(get_frame(run_id, frame_id)))

    @app.get("/api/runs/{run_id}/frames/{frame_id}/annotated")
    def annotated(run_id: str, frame_id: int):
        row = get_frame(run_id, frame_id)
        image = decode(frame_path(row).read_bytes())
        # 绘图使用预测四点，文字仅英文模型类名；不修改检测结果坐标。
        thickness = max(1, round(min(image.shape[:2]) / 500))
        for det in row["data"]["detections"]:
            points = np.rint(det["polygon"]).astype(np.int32)
            color = (70, 190, 40)
            cv2.polylines(image, [points], True, color, thickness, cv2.LINE_AA)
            x = int(np.clip(points[0, 0], 0, max(0, image.shape[1] - 200)))
            y = int(np.clip(points[0, 1] - 6, 18, image.shape[0] - 2))
            cv2.putText(image, f"{det['class_name']} {det['confidence']:.2f}", (x, y),
                        cv2.FONT_HERSHEY_SIMPLEX, .5 * thickness, color, thickness, cv2.LINE_AA)
        ok, encoded = cv2.imencode(".png", image)
        if not ok:
            fail(500, "ENCODE_FAILED", "可视化图片编码失败")
        return Response(encoded.tobytes(), media_type="image/png",
                        headers={"Content-Disposition": f'attachment; filename="{run_id}_{frame_id}.png"'})

    @app.get("/api/runs/{run_id}/export")
    def export(run_id: str, format: Literal["json", "csv"] = "json"):
        run = get_run(run_id)
        if run["status"] not in TERMINAL:
            fail(409, "RUN_ACTIVE", "请等待任务结束后导出完整结果")

        def all_frames():
            page = 1
            while True:
                batch = app.state.store.frames(run_id, page, 100)
                yield from batch["items"]
                if page * 100 >= batch["total"]:
                    break
                page += 1

        def generate():
            if format == "json":
                yield '{"protocol_version":"1.0","run":' + json.dumps(run, ensure_ascii=False, allow_nan=False) + ',"frames":['
                for index, item in enumerate(all_frames()):
                    yield ("," if index else "") + json.dumps(item, ensure_ascii=False, allow_nan=False)
                yield "]}"
            else:
                yield "\ufeff"
                buf = io.StringIO()
                writer = csv.writer(buf)
                writer.writerow(["run_id", "frame_id", "name", "frame_status", "error", "class_id", "class_name", "confidence", "polygon_pixels", "total_ms"])
                yield buf.getvalue()
                for item in all_frames():
                    for det in item["detections"] or [None]:
                        buf.seek(0); buf.truncate(0)
                        # 防止电子表格将文件名/类别解释为公式。
                        def safe(value):
                            value = str(value or "")
                            return "'" + value if value.startswith(("=", "+", "-", "@", "\t", "\r", "\n")) else value
                        writer.writerow([run_id, item["id"], safe(item["name"]), item["status"], safe(item["error"]),
                                         det["class_id"] if det else "", safe(det["class_name"]) if det else "",
                                         det["confidence"] if det else "", json.dumps(det["polygon"]) if det else "",
                                         item["timing_ms"].get("total", "")])
                        yield buf.getvalue()
        return StreamingResponse(generate(), media_type="application/json" if format == "json" else "text/csv; charset=utf-8",
                                 headers={"Content-Disposition": f'attachment; filename="{run_id}.{format}"'})

    @app.get("/api/{path:path}")
    def missing_api(path: str):
        fail(404, "NOT_FOUND", "API 不存在")

    dist = ROOT / "frontend/dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    else:
        @app.get("/")
        def no_frontend():
            return {"message": "前端尚未构建，请在 frontend 执行 npm install && npm run build", "docs": "/docs"}
    return app


app = create_app()
