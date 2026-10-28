"""独立 PostgreSQL 持久化；帧与计数同一事务提交，单实例 advisory lock。"""
import threading

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


class Store:
    def __init__(self, url):
        self.lock = threading.RLock()
        self.conn = psycopg.connect(url, autocommit=True, row_factory=dict_row, connect_timeout=5)
        with self.lock:
            dbname = self.conn.execute("SELECT current_database() AS name").fetchone()["name"]
            if dbname != "factory_demo" and not dbname.startswith("factory_demo_test_"):
                self.conn.close()
                raise RuntimeError("拒绝连接非 factory_demo 数据库；请使用独立新库")
            # 锁名固定，作用域为本数据库；拒绝多 worker/第二个写入实例。
            locked = self.conn.execute("SELECT pg_try_advisory_lock(71825011, hashtext(current_schema())) AS ok").fetchone()["ok"]
            if not locked:
                self.conn.close()
                raise RuntimeError("该数据库已有 Factory Demo 实例；只允许单进程单 worker")
            self.conn.execute("""CREATE TABLE IF NOT EXISTS factory_runs (
                id text PRIMARY KEY, created_at timestamptz NOT NULL, status text NOT NULL,
                data jsonb NOT NULL)""")
            self.conn.execute("""CREATE TABLE IF NOT EXISTS factory_frames (
                run_id text NOT NULL REFERENCES factory_runs(id), frame_id integer NOT NULL,
                data jsonb NOT NULL, image_path text, PRIMARY KEY(run_id, frame_id))""")
            self.conn.execute("CREATE INDEX IF NOT EXISTS factory_runs_created ON factory_runs(created_at DESC)")
            rows = self.conn.execute("SELECT data FROM factory_runs WHERE status NOT IN ('completed','stopped','failed','interrupted')").fetchall()
            for row in rows:
                run = row["data"]
                run.update(status="interrupted", error="上次服务中断，未自动恢复；重新运行将创建新任务")
                from datetime import datetime, timezone
                run["finished_at"] = datetime.now(timezone.utc).isoformat()
                self.save_run(run)

    def ping(self):
        with self.lock:
            self.conn.execute("SELECT 1")

    def save_run(self, run):
        with self.lock:
            self.conn.execute("""INSERT INTO factory_runs(id, created_at, status, data) VALUES(%s,%s,%s,%s)
                ON CONFLICT(id) DO UPDATE SET status=EXCLUDED.status, data=EXCLUDED.data""",
                (run["id"], run["created_at"], run["status"], Jsonb(run)))

    def save_frame(self, run, frame, image_path):
        with self.lock, self.conn.transaction():
            self.conn.execute("INSERT INTO factory_frames(run_id,frame_id,data,image_path) VALUES(%s,%s,%s,%s)",
                              (run["id"], frame["id"], Jsonb(frame), str(image_path) if image_path else None))
            self.save_run(run)

    def get_run(self, run_id):
        with self.lock:
            row = self.conn.execute("SELECT data FROM factory_runs WHERE id=%s", (run_id,)).fetchone()
            return row["data"] if row else None

    def latest_run(self):
        with self.lock:
            row = self.conn.execute("SELECT data FROM factory_runs ORDER BY created_at DESC LIMIT 1").fetchone()
            return row["data"] if row else None

    def runs(self, page, page_size):
        with self.lock:
            total = self.conn.execute("SELECT count(*) AS n FROM factory_runs").fetchone()["n"]
            rows = self.conn.execute("SELECT data FROM factory_runs ORDER BY created_at DESC LIMIT %s OFFSET %s",
                                     (page_size, (page - 1) * page_size)).fetchall()
            return {"items": [r["data"] for r in rows], "total": total, "page": page, "page_size": page_size}

    def frames(self, run_id, page, page_size):
        with self.lock:
            total = self.conn.execute("SELECT count(*) AS n FROM factory_frames WHERE run_id=%s", (run_id,)).fetchone()["n"]
            rows = self.conn.execute("SELECT data FROM factory_frames WHERE run_id=%s ORDER BY frame_id LIMIT %s OFFSET %s",
                                     (run_id, page_size, (page-1)*page_size)).fetchall()
            return {"items": [r["data"] for r in rows], "total": total, "page": page, "page_size": page_size}

    def frame(self, run_id, frame_id):
        with self.lock:
            return self.conn.execute("SELECT data,image_path FROM factory_frames WHERE run_id=%s AND frame_id=%s",
                                     (run_id, frame_id)).fetchone()

    def close(self):
        with self.lock:
            self.conn.close()

