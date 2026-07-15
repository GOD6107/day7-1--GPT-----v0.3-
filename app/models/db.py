# app/models/db.py
from __future__ import annotations
import sqlite3
import os
from datetime import datetime
from config import AppConfig

DB_PATH = str(AppConfig.DATABASE_PATH)

def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def record_audit(action, username="system", ip="", detail=""):
    """写入审计日志，失败不影响主流程"""
    try:
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO audit_logs (username, action, ip, detail, created_at) VALUES (?,?,?,?,?)",
                (username or "anonymous", action, ip, detail, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            )
    except:
        pass

def init_db():
    with get_connection() as conn:
        # 创建 users 表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                role_id INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'active',
                last_login TEXT,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            )
        """)
        # roles
        conn.execute("""
            CREATE TABLE IF NOT EXISTS roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                is_system INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active'
            )
        """)
        # functions
        conn.execute("""
                CREATE TABLE IF NOT EXISTS functions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                parent_id INTEGER DEFAULT 0,
                name TEXT NOT NULL,
                route TEXT,
                sort_order INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active'
            )        """)
        # role_function_map
        conn.execute("""
            CREATE TABLE IF NOT EXISTS role_function_map (
                role_id INTEGER,
                function_id INTEGER,
                sort_order INTEGER DEFAULT 0,
                UNIQUE(role_id, function_id)
            )
        """)
        # audit_logs
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT,
                action TEXT,
                ip TEXT,
                detail TEXT,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            )
        """)
        # watch_sources
        conn.execute("""
            CREATE TABLE IF NOT EXISTS watch_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                url_template TEXT NOT NULL,
                headers_json TEXT DEFAULT '{}',
                page_step INTEGER DEFAULT 10,
                parser_type TEXT DEFAULT 'generic',
                enabled INTEGER DEFAULT 1,
                status TEXT DEFAULT 'active',
                description TEXT,
                last_test_status TEXT,
                last_test_message TEXT
            )
        """)
        # warehouse_items
        conn.execute("""
            CREATE TABLE IF NOT EXISTS warehouse_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id INTEGER,
                source_name TEXT,
                keyword TEXT,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                summary TEXT,
                raw_json TEXT,
                deep_collected INTEGER DEFAULT 0,
                deep_data TEXT,
                status TEXT DEFAULT 'active',
                created_at TEXT DEFAULT (datetime('now','localtime'))
            )
        """)
        # model_engines
        conn.execute("""
            CREATE TABLE IF NOT EXISTS model_engines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                provider TEXT,
                base_url TEXT,
                api_key TEXT,
                model_name TEXT,
                category TEXT DEFAULT 'text',
                system_prompt TEXT,
                top_value REAL DEFAULT 0.8,
                context_count INTEGER DEFAULT 8,
                is_default INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active',
                token_prompt INTEGER DEFAULT 0,
                token_completion INTEGER DEFAULT 0,
                token_total INTEGER DEFAULT 0,
                last_used_at TEXT
            )
        """)
        # 用户对话历史
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_histories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                query TEXT,
                response TEXT,
                response_type TEXT DEFAULT 'text',
                source TEXT DEFAULT '',
                meta TEXT DEFAULT '{}',
                created_at TEXT DEFAULT (datetime('now','localtime'))
            )
        """)
        # 索引
        conn.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_warehouse_keyword ON warehouse_items(keyword)")

        # 种子数据
        seed_defaults(conn)
        conn.commit()

def seed_defaults(conn):
    # 默认角色
    conn.execute("INSERT OR IGNORE INTO roles (code, name, description, is_system) VALUES ('admin', '系统管理员', '后台管理', 1)")
    conn.execute("INSERT OR IGNORE INTO roles (code, name, description) VALUES ('user', '普通用户', '前台访问')")

    # 默认功能（简化）
    functions = [
        ('dashboard', 0, '总览', '/admin', 10),
        ('users', 0, '用户管理', '/admin/users', 20),
        ('roles', 0, '角色管理', '/admin/roles', 30),
        ('functions', 0, '功能管理', '/admin/functions', 40),
        ('menus', 0, '菜单管理', '/admin/menus', 50),
        ('collect', 0, '瞭望管理', '/admin/watch', 60),
        ('sources', 0, '瞭源管理', '/admin/sources', 70),
        ('warehouse', 0, '数据仓库', '/admin/warehouse', 80),
        ('models', 0, '模型引擎', '/admin/models', 90),
    ]
    id_map = {}
    for code, parent, name, route, order in functions:
        parent_id = id_map.get(parent, 0) if isinstance(parent, str) else parent
        conn.execute("INSERT OR IGNORE INTO functions (code, parent_id, name, route, sort_order) VALUES (?,?,?,?,?)",
                     (code, parent_id, name, route, order))
        row = conn.execute("SELECT id FROM functions WHERE code=?", (code,)).fetchone()
        if row:
            id_map[code] = row[0]

    admin_role = conn.execute("SELECT id FROM roles WHERE code='admin'").fetchone()
    if admin_role:
        admin_id = admin_role[0]
        conn.execute("DELETE FROM role_function_map WHERE role_id=?", (admin_id,))
        funcs = conn.execute("SELECT id FROM functions ORDER BY sort_order").fetchall()
        for idx, f in enumerate(funcs, 1):
            conn.execute("INSERT INTO role_function_map (role_id, function_id, sort_order) VALUES (?,?,?)",
                         (admin_id, f[0], idx))

    # 修复旧数据库中可能存在的文字错别字
    conn.execute("UPDATE functions SET name='瞭望管理' WHERE code='collect' AND name!='瞭望管理'")
    conn.execute("UPDATE functions SET name='瞭源管理' WHERE code='sources' AND name!='瞭源管理'")
