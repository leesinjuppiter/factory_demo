"""创建独立本机数据库/角色；可从已有 .env 读取管理员连接，不输出密码。"""
import argparse
import os
import secrets
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
from psycopg import sql
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-env", type=Path, help="仅用于读取本地管理员 DATABASE_URL")
    args = parser.parse_args()
    target = ROOT / ".env"
    if target.exists():
        with psycopg.connect(dotenv_values(target)["DATABASE_URL"], connect_timeout=5) as conn:
            db = conn.execute("SELECT current_database()").fetchone()[0]
        print(f"现有配置可连接：{db}；未覆盖配置或修改数据库")
        return
    source = dotenv_values(args.from_env) if args.from_env else os.environ
    url = source.get("FACTORY_ADMIN_DATABASE_URL") or source.get("DATABASE_URL")
    if not url:
        raise SystemExit("请用 --from-env 指定管理员 .env，或设置 FACTORY_ADMIN_DATABASE_URL")
    url = url.replace("postgresql+psycopg://", "postgresql://").replace("postgresql+psycopg2://", "postgresql://")
    parsed = urlsplit(url)
    if parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
        raise SystemExit("本脚本仅接受本机 PostgreSQL")
    admin_url = urlunsplit((parsed.scheme, parsed.netloc, "/postgres", parsed.query, ""))
    password = secrets.token_hex(24)
    with psycopg.connect(admin_url, autocommit=True, connect_timeout=5) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname='factory_demo'").fetchone()
        role = conn.execute("SELECT 1 FROM pg_roles WHERE rolname='factory_demo'").fetchone()
        if exists or role:
            raise SystemExit("factory_demo 数据库或角色已存在，拒绝覆盖；请手工配置 .env")
        conn.execute(sql.SQL("CREATE ROLE factory_demo LOGIN PASSWORD {}").format(sql.Literal(password)))
        conn.execute("CREATE DATABASE factory_demo OWNER factory_demo")
    port = parsed.port or 5432
    # 仅新项目的连接凭据写入 .env；不复制原管理员密码。
    with target.open("x", encoding="utf-8") as output:
        output.write(f"DATABASE_URL=postgresql://factory_demo:{password}@127.0.0.1:{port}/factory_demo\n")
    print("独立数据库 factory_demo 和非超级用户 factory_demo 已建立；连接保存在 .env（已忽略入库）")


if __name__ == "__main__":
    main()
