"""Read-only display entry for a mapped cloud port; the full API stays local."""
import asyncio
from contextlib import asynccontextmanager, suppress
import logging
import os
from pathlib import Path
import re
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, HTTPException, Path as RoutePath, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, Response
from starlette.middleware.trustedhost import TrustedHostMiddleware
from websockets.asyncio.client import connect
from websockets.exceptions import WebSocketException

DIST = Path(__file__).resolve().parents[1] / "frontend/dist"
UPSTREAM = "http://127.0.0.1:8765"


def create_display_app(public_host=None, transport=None):
    host = public_host if public_host is not None else os.getenv("FACTORY_DISPLAY_HOST", "")
    if host and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{0,252}", host):
        raise ValueError("FACTORY_DISPLAY_HOST 必须为单个主机名，不含协议、端口或通配符")
    hosts = ["localhost", "127.0.0.1", "testserver"] + ([host] if host else [])
    dist = DIST

    @asynccontextmanager
    async def lifespan(app):
        async with httpx.AsyncClient(base_url=UPSTREAM, trust_env=False, timeout=10,
                                     transport=transport, limits=httpx.Limits(max_connections=16)) as client:
            app.state.upstream = client
            yield

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)

    @app.middleware("http")
    async def rejected_host_log(request, call_next):
        response = await call_next(request)
        if response.status_code == 400:
            logging.getLogger("factory_demo.display").warning("Rejected display Host: %r", request.headers.get("host", "")[:253])
        return response

    @app.get("/", response_class=HTMLResponse)
    @app.get("/index.html", response_class=HTMLResponse)
    async def index():
        if not (dist / "index.html").is_file():
            raise HTTPException(503, "请先构建展示前端")
        text = (dist / "index.html").read_text(encoding="utf-8")
        return HTMLResponse(text.replace("</head>", '<meta name="factory-display-readonly" content="true"></head>'))

    @app.get("/assets/{name}")
    async def asset(name: str):
        if not re.fullmatch(r"(?:display|style)-[A-Za-z0-9_-]+\.(?:js|css)", name):
            raise HTTPException(404)
        path = dist / "assets" / name
        if not path.is_file():
            raise HTTPException(404)
        return FileResponse(path)

    async def proxy(path):
        try:
            response = await app.state.upstream.get(path)
        except httpx.HTTPError:
            raise HTTPException(503, "展示结果服务暂不可用") from None
        return Response(response.content, status_code=response.status_code,
                        headers={"Content-Type": response.headers.get("content-type", "application/octet-stream"),
                                 "Cache-Control": "no-store"})

    @app.get("/api/display/snapshot")
    async def snapshot():
        return await proxy("/api/display/snapshot")

    @app.get("/api/display/previews/{identity}.jpg")
    async def preview(identity: str = RoutePath(pattern=r"^[0-9a-f]{32}$")):
        return await proxy(f"/api/display/previews/{identity}.jpg")

    @app.websocket("/api/display/ws")
    async def stream(ws: WebSocket):
        origin = ws.headers.get("origin")
        if origin and urlsplit(origin).hostname not in hosts:
            await ws.close(code=1008)
            return
        try:
            async with connect("ws://127.0.0.1:8765/api/display/ws", origin=UPSTREAM,
                               max_size=2**20, max_queue=1, open_timeout=5) as upstream:
                await ws.accept()

                async def send():
                    async for message in upstream:
                        await asyncio.wait_for(ws.send_text(message), timeout=5)

                async def receive():
                    message = await ws.receive()
                    if message["type"] != "websocket.disconnect":
                        await ws.close(code=1008, reason="展示通道只读")

                tasks = [asyncio.create_task(send()), asyncio.create_task(receive())]
                try:
                    await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                finally:
                    for task in tasks:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
        except (OSError, TimeoutError, WebSocketException):
            pass
        finally:
            with suppress(RuntimeError, WebSocketDisconnect):
                await ws.close(code=1013)

    return app


app = create_display_app()
