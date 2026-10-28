"""Engine-neutral display v1 projection. No database, HTTP or model dependency."""
import math
from copy import deepcopy

SCHEMA_VERSION = "1.0"
ANGLE_CONVENTION = "long_axis_clockwise_from_positive_x_mod_180"
ENGINE_LABELS = {"pytorch": "PyTorch · YOLOv5-OBB", "openvino": "OpenVINO", "tensorrt": "TensorRT"}


def finite(value, *, nullable=True):
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("协议数值必须有限")
    return value


def detection_view(item, geometry_type="obb"):
    points = item.get("polygon_px", item.get("polygon"))
    if not isinstance(points, (list, tuple)) or len(points) != 4:
        raise ValueError("二维检测必须提供四个顺序角点")
    polygon = []
    for point in points:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise ValueError("角点必须为 [x,y]")
        polygon.append([float(finite(v, nullable=False)) for v in point])
    confidence = float(finite(item.get("confidence"), nullable=False))
    if not 0 <= confidence <= 1:
        raise ValueError("置信度必须在 0..1")
    edges = [(polygon[(i+1) % 4][0]-polygon[i][0], polygon[(i+1) % 4][1]-polygon[i][1]) for i in range(4)]
    lengths = [math.hypot(*edge) for edge in edges]
    if min(lengths) <= 0:
        raise ValueError("检测框包含退化边")
    crosses = [edges[i][0]*edges[(i+1) % 4][1]-edges[i][1]*edges[(i+1) % 4][0] for i in range(4)]
    if not (all(c > 0 for c in crosses) or all(c < 0 for c in crosses)):
        raise ValueError("四角点必须依序组成非退化凸四边形")
    # Only numerical square degeneracy is rejected; task-specific near-square
    # reliability is not calibrated, so this is a geometric direction, not a pose.
    longest = max(range(4), key=lambda i: lengths[i])
    valid = geometry_type == "obb" and not math.isclose(max(lengths), min(lengths), rel_tol=1e-6, abs_tol=1e-8)
    angle = math.degrees(math.atan2(edges[longest][1], edges[longest][0])) % 180 if valid else None
    return {"id": item["id"], "class_id": item["class_id"], "class_name": str(item["class_name"]),
            "confidence": confidence, "geometry_type": geometry_type, "polygon_px": polygon,
            "center_px": [sum(p[a] for p in polygon)/4 for a in (0, 1)],
            "angle_deg": angle, "angle_convention": ANGLE_CONVENTION,
            "orientation_valid": valid, "track_id": None}


def safe_error(value, code):
    # Internal exception text may contain filesystem paths. It stays in admin
    # records/logs; the read-only public display gets a stable diagnostic code.
    if not value:
        return None
    return {"code": code, "message": "处理失败，请在后台查看诊断；当前状态不代表未检出目标。"}


def stream_view(run):
    if run is None:
        return None
    model = run.get("model") or {}
    engine = (run.get("config") or {}).get("engine", "")
    classes = [{k: c.get(k) for k in ("id", "name", "label", "color")} for c in model.get("classes", [])]
    return {"session_id": run["id"], "source_id": run["source_id"], "source_label": run["source_label"],
            "mode": "continuous" if run.get("total") is None else "finite", "status": run["status"],
            "model": {"id": model.get("name"), "version": model.get("sha256"),
                      "name": model.get("name"), "device": model.get("device")},
            "engine_label": ENGINE_LABELS.get(engine, str(engine)), "classes": classes,
            "class_catalog_version": model.get("sha256"),
            **{k: deepcopy(run.get(k)) for k in ("class_counts", "processed", "total", "succeeded", "failed", "timings")},
            "error": safe_error(run.get("error"), "RUN_FAILED")}


def frame_view(run, frame):
    if frame is None or frame.get("run_id") != run["id"]:
        return None
    key = frame.get("capture_key") or {"source_id": run["source_id"], "session_id": run["id"], "frame_id": str(frame["id"])}
    key = {k: str(key[k]) for k in ("source_id", "session_id", "frame_id")}
    if not all(key.values()):
        raise ValueError("帧身份字段不能为空")
    geometry_type = (run.get("model") or {}).get("box_type", "obb")
    return {"frame_key": key, "stream_session_id": run["id"], "id": str(frame["id"]),
            "name": frame["name"], "status": frame["status"], "width": frame["width"], "height": frame["height"],
            "coordinate_space": "source_pixels", "detections": [detection_view(d, geometry_type) for d in frame["detections"]],
            "timing_ms": deepcopy(frame.get("timing_ms", {})), "created_at": frame.get("created_at"),
            "capture_time": frame.get("capture_time"), "capture_clock_domain": frame.get("capture_clock_domain"),
            "published_at": frame.get("published_at"), "preview": None,
            "preview_status": "pending" if frame["status"] == "ok" else "none",
            "error": safe_error(frame.get("error"), "FRAME_FAILED")}
