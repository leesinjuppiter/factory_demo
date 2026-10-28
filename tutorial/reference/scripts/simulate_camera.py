"""模拟相机：先关闭图片，再原子发布 ready 清单；绝不覆盖来源数据。"""
import argparse
import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path


def publish(output, payload, suffix, source_id, session_id, frame_id):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    stem = f"{stamp}_{session_id}_{frame_id:09d}"
    name = stem + suffix.lower()
    temporary = output / (name + ".part")
    with temporary.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, output / name)
    meta = {"schema_version": "1.0", "source_id": source_id, "session_id": session_id,
            "frame_id": str(frame_id), "image": name, "size": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(), "capture_time": None,
            "published_at": datetime.now(timezone.utc).isoformat(), "simulated": True}
    ready = output / (stem + ".ready.json")
    temporary = output / (stem + ".ready.part")
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(meta, stream, ensure_ascii=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, ready)
    return ready


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--source-id", default="camera_inbox")
    parser.add_argument("--count", type=int, default=50)
    parser.add_argument("--fps", type=float, default=5)
    args = parser.parse_args()
    import re
    if args.count < 1 or args.count > 10000 or not 0 < args.fps <= 1000 or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", args.source_id):
        parser.error("count 须为1..10000，fps 为(0,1000]，source-id 为字母数字下划线短横线")
    source, output = args.input_dir.resolve(), args.output_dir.resolve()
    if output == source or output.is_relative_to(source):
        parser.error("输出目录不能位于输入图片目录内")
    files = sorted(p for p in source.iterdir() if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp"})
    if not files:
        parser.error("输入目录没有支持的图片")
    output.mkdir(parents=True, exist_ok=True)
    session = uuid.uuid4().hex
    started = time.perf_counter()
    late = 0
    for index in range(args.count):
        tick = time.perf_counter()
        item = files[index % len(files)]
        if not 0 < item.stat().st_size <= 20 * 1024 ** 2:
            parser.error("输入图片超过当前20MiB限制或为空")
        payload = item.read_bytes()
        publish(output, payload, item.suffix, args.source_id, session, index + 1)
        remaining = 1 / args.fps - (time.perf_counter() - tick)
        if remaining < 0:
            late += 1
        if index + 1 < args.count and remaining > 0:
            time.sleep(remaining)
    elapsed = time.perf_counter() - started
    print(json.dumps({"session_id": session, "published": args.count, "requested_fps": args.fps,
                      "elapsed_seconds": elapsed, "work_rate_fps": args.count / elapsed,
                      "late_frames": late, "capture_time": None,
                      "note": "文件落盘模拟；真实拍摄时间未知；此速率不是推理吞吐或生产相机验收"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
