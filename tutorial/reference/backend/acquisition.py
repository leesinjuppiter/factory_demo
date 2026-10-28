"""完成发布的目录帧；回执独立于源图片，不删除或改写相机文件。"""
import hashlib
import json
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path

from .images import InputError
from .settings import EXTENSIONS, LIMITS


class InboxSource:
    """单消费者 ready manifest 队列。容量超限明确失败，绝不静默丢待检帧。"""

    def __init__(self, root, receipt_path):
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise InputError("相机接收目录不存在，请先运行模拟拍照脚本")
        receipt_path = Path(receipt_path)
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        self.receipts = sqlite3.connect(receipt_path)
        self.receipts.execute("CREATE TABLE IF NOT EXISTS receipts (name TEXT PRIMARY KEY, digest TEXT NOT NULL)")
        self.receipts.execute("CREATE TABLE IF NOT EXISTS identities (identity TEXT PRIMARY KEY, name TEXT NOT NULL)")
        self.pending = []
        self.pending_count = 0
        self.last_scan = 0.0

    def _read(self, path):
        if path.is_symlink() or path.stat().st_size > 16384:
            raise InputError("相机发布清单无效：符号链接或清单超过16KiB")
        payload = path.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        done = self.receipts.execute("SELECT digest FROM receipts WHERE name=?", (path.name,)).fetchone()
        if done:
            if done[0] != digest:
                raise InputError("已消费清单被修改；请使用新的帧身份和文件名")
            return None
        try:
            meta = json.loads(payload)
            if meta.get("schema_version") != "1.0":
                raise ValueError("schema")
            name = meta["image"]
            if not isinstance(name, str) or name != Path(name).name or '/' in name or '\\' in name:
                raise ValueError("image name")
            image = self.root / name
            if image.is_symlink() or image.resolve().parent != self.root or image.suffix.lower() not in EXTENSIONS:
                raise ValueError("image path")
            key = {k: str(meta[k]) for k in ("source_id", "session_id", "frame_id")}
            if not all(re.fullmatch(r"[A-Za-z0-9_-]{1,100}", v) for v in key.values()):
                raise ValueError("identity")
            if not key["frame_id"].isdigit():
                raise ValueError("sequence")
            identity = json.dumps(key, sort_keys=True)
            if self.receipts.execute("SELECT 1 FROM identities WHERE identity=?", (identity,)).fetchone():
                raise ValueError("previously consumed identity")
            expected = meta["sha256"]
            if not isinstance(expected, str) or not re.fullmatch(r"[a-f0-9]{64}", expected):
                raise ValueError("digest")
            published = datetime.fromisoformat(meta["published_at"])
            if published.tzinfo is None:
                raise ValueError("timezone")
            captured = meta.get("capture_time")
            if captured is not None and datetime.fromisoformat(captured).tzinfo is None:
                raise ValueError("capture timezone")
            stat = image.stat()
            if type(meta["size"]) is not int or stat.st_size != meta["size"] or not 0 < stat.st_size <= LIMITS["max_file_bytes"]:
                raise ValueError("size")
        except (KeyError, ValueError, TypeError, OSError, AttributeError) as exc:
            raise InputError("相机发布清单或对应图片无效；请检查身份、时间、完整写入及20MiB上限") from exc
        return {"path": image, "name": name, "size": stat.st_size, "mtime": stat.st_mtime_ns,
                "capture_key": key, "capture_time": captured, "published_at": meta["published_at"],
                "expected_sha256": expected, "manifest_name": path.name, "manifest_digest": digest,
                "_order": (published.timestamp(), key["session_id"], int(key["frame_id"]))}

    def next_item(self):
        if not self.pending:
            now = time.monotonic()
            if now - self.last_scan < .1:
                return None
            self.last_scan = now
            found = []
            identities = set()
            # 周期补扫不会依赖文件系统通知；只把已发布清单加入内存。
            for path in self.root.glob("*.ready.json"):
                item = self._read(path)
                if item is None:
                    continue
                identity = tuple(item["capture_key"].values())
                if identity in identities:
                    raise InputError("不同清单重复使用同一个相机帧身份")
                identities.add(identity)
                found.append(item)
                if len(found) > LIMITS["max_images"]:
                    raise InputError("相机未消费清单超过10000条，停止任务；未删除或跳过源图片")
            self.pending = sorted(found, key=lambda item: item["_order"], reverse=True)
        self.pending_count = len(self.pending)
        return self.pending.pop() if self.pending else None

    def ack(self, item):
        # 仅在业务结果已提交后调用。回执故障由上层结束任务，不隐式继续。
        self.receipts.execute("INSERT INTO receipts(name,digest) VALUES(?,?)",
                              (item["manifest_name"], item["manifest_digest"]))
        self.receipts.execute("INSERT INTO identities(identity,name) VALUES(?,?)",
                              (json.dumps(item["capture_key"], sort_keys=True), item["manifest_name"]))
        self.receipts.commit()
        self.pending_count = len(self.pending)

    def close(self):
        self.receipts.close()
