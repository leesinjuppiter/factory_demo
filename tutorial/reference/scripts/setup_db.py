"""仅由学习者主动运行：新建教学专用库和角色，不读取原项目凭据。"""
import getpass
import secrets
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
import psycopg
from psycopg import sql
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
DB = 'factory_demo_test_tutorial'
ROLE = 'factory_demo_tutorial'

def main():
    target = ROOT / '.env'
    if target.exists():
        with psycopg.connect(dotenv_values(target)['DATABASE_URL'], connect_timeout=5) as conn:
            name = conn.execute('SELECT current_database()').fetchone()[0]
        if name != DB:
            raise SystemExit('教学配置指向错误数据库，请人工检查；未修改数据库')
        print('教学数据库连接成功；没有重建或覆盖。')
        return
    url = getpass.getpass('输入本机 PostgreSQL 管理员连接 URL（隐藏输入，仅本次使用）：')
    parsed = urlsplit(url)
    if parsed.scheme not in ('postgresql','postgres') or parsed.hostname not in ('localhost','127.0.0.1','::1'):
        raise SystemExit('只接受本机 PostgreSQL URL')
    admin = urlunsplit((parsed.scheme,parsed.netloc,'/postgres',parsed.query,''))
    password = secrets.token_hex(24)
    with psycopg.connect(admin,autocommit=True,connect_timeout=5) as conn:
        if conn.execute('SELECT 1 FROM pg_database WHERE datname=%s',(DB,)).fetchone() or conn.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(ROLE,)).fetchone():
            raise SystemExit('教学库或角色已经存在，拒绝覆盖。请人工配置练习目录的 .env。')
        conn.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {}').format(sql.Identifier(ROLE),sql.Literal(password)))
        conn.execute(sql.SQL('CREATE DATABASE {} OWNER {}').format(sql.Identifier(DB),sql.Identifier(ROLE)))
    host = '['+parsed.hostname+']' if ':' in parsed.hostname else parsed.hostname
    with target.open('x',encoding='utf-8') as f:
        f.write(f'DATABASE_URL=postgresql://{ROLE}:{password}@{host}:{parsed.port or 5432}/{DB}\n')
    print('教学库已建立，普通角色连接写入练习目录 .env；未保存管理员连接。')

if __name__=='__main__': main()
