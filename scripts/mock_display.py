"""独立展示协议后端：无数据库、无模型，同一份 frontend/dist 验证 HBB/OBB。"""
import argparse
import asyncio
import json
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import cv2
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parents[1]


def snapshot(sequence):
    obb = sequence % 20 >= 10
    classes = [{"id": i, "name": f"mock_class_{i}", "label": f"模拟类别 {i}", "color": ["#36c8b0", "#ffb86b", "#84b9ff"][i % 3]}
               for i in range(8 if obb else 3)]
    polygon = [[120., 90.], [320., 150.], [290., 250.], [90., 190.]] if obb else [[120., 90.], [320., 90.], [320., 230.], [120., 230.]]
    import math
    key = "obb" if obb else "hbb"
    model = {"id": f"independent-mock-{key}", "version": key, "name": f"模拟 {key.upper()} · 无真实推理", "device": "mock"}
    detected = {"id": "fixture-1", "class_id": 1, "class_name": "mock_class_1", "confidence": .9,
                "geometry_type": key, "polygon_px": polygon,
                "center_px": [sum(p[i] for p in polygon) / 4 for i in (0, 1)],
                "angle_deg": math.degrees(math.atan2(60, 200)) if obb else None,
                "angle_convention": "long_axis_clockwise_from_positive_x_mod_180", "orientation_valid": obb, "track_id": None}
    return {"schema_version": "1.0", "type": "snapshot", "revision": sequence,
            "stream": {"session_id": "mock-session", "source_id": "mock", "source_label": "独立协议模拟（不是性能/准确率数据）",
                       "mode": "continuous", "status": "running", "model": model, "engine_label": "独立 Mock 后端",
                       "class_catalog_version": key, "classes": classes, "class_counts": {},
                       "processed": sequence, "total": None, "succeeded": sequence, "failed": 0,
                       "timings": {"mean_ms": None, "p50_ms": None, "p95_ms": None, "fps": None}, "error": None},
            "frame": {"frame_key": {"source_id": "mock", "session_id": "mock-session", "frame_id": str(sequence)},
                      "stream_session_id": "mock-session", "id": str(sequence), "name": f"mock-{key}-{sequence}",
                      "status": "ok", "width": 640, "height": 360, "coordinate_space": "source_pixels",
                      "detections": [] if sequence % 7 == 0 else [detected], "timing_ms": {},
                      "created_at": datetime.now(timezone.utc).isoformat(), "capture_time": None,
                      "preview_status": "ready", "preview": {"id": f"{key}-{sequence}",
                          "url": f"/api/display/previews/{key}-{sequence}.jpg", "width": 320, "height": 180,
                          "sx": .5, "sy": .5, "ox": 0, "oy": 0}, "error": None}}


@asynccontextmanager
async def lifespan(app):
    app.state.latest = snapshot(1)
    app.state.images = {}
    for index, kind in enumerate(("hbb", "obb")):
        pixels = np.full((180, 320, 3), (45 + index * 30, 52, 38), np.uint8)
        cv2.putText(pixels, "MOCK " + kind.upper(), (25, 155), cv2.FONT_HERSHEY_SIMPLEX, .7, (230, 230, 230), 2)
        cv2.rectangle(pixels, (60, 45), (160, 115), (150, 100, 70), -1)
        app.state.images[kind] = cv2.imencode('.jpg', pixels)[1].tobytes()
    async def produce():
        sequence = 1
        while True:
            await asyncio.sleep(.2)
            sequence += 1
            app.state.latest = snapshot(sequence)
    task = asyncio.create_task(produce())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError): await task


app = FastAPI(title="Factory Display Independent Mock", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?", allow_methods=["GET"])


@app.get('/api/display/snapshot')
def get_snapshot():
    return app.state.latest


@app.get('/api/display/previews/{name}')
def preview(name: str):
    import re
    match = re.fullmatch(r'(hbb|obb)-[0-9]{1,12}\.jpg', name)
    if not match:
        return Response(status_code=404)
    return Response(app.state.images[match[1]], media_type='image/jpeg', headers={'Cache-Control':'private, max-age=60, immutable'})


@app.websocket('/api/display/ws')
async def live(ws: WebSocket):
    origin = ws.headers.get('origin')
    if origin and urlsplit(origin).hostname not in {'localhost', '127.0.0.1'}:
        await ws.close(code=1008)
        return
    await ws.accept()
    async def send():
        previous = None
        while True:
            current = app.state.latest
            if current['revision'] != previous:
                await asyncio.wait_for(ws.send_text(json.dumps(current)), 3)
                previous = current['revision']
            await asyncio.sleep(.05)
    sender = asyncio.create_task(send())
    try:
        # This endpoint is read-only, just like the real presentation stream.
        await ws.receive_text()
        await ws.close(code=1008)
    except WebSocketDisconnect:
        pass
    finally:
        sender.cancel()
        with suppress(asyncio.CancelledError, Exception): await sender


dist = ROOT / 'frontend/dist'
if dist.exists():
    app.mount('/', StaticFiles(directory=dist, html=True), name='display')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8879)
    args = parser.parse_args()
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=args.port, log_level='info')
