from __future__ import annotations
import hashlib
import json
import secrets
import sqlite3
from datetime import datetime
from app.models.db import get_connection
from config import AppConfig

def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _hash_password(password, salt, iterations=200000):
    return hashlib.pbkdf2_hmac('sha256', password.encode(), salt, iterations).hex()

def _new_salt():
    return secrets.token_bytes(16).hex()

class UserRepository:
    @staticmethod
    def get_user_by_username(username):
        with get_connection() as conn:
            return conn.execute("""
                SELECT u.*, r.code as role_code, r.name as role_name
                FROM users u LEFT JOIN roles r ON u.role_id = r.id
                WHERE u.username = ?
            """, (username,)).fetchone()

    @staticmethod
    def get_user_by_id(user_id):
        with get_connection() as conn:
            return conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()

    @staticmethod
    def list_users(keyword='', status='', role_id=None, page=1, per_page=20):
        cond = []
        params = []
        if keyword:
            cond.append("username LIKE ?")
            params.append(f"%{keyword}%")
        if status:
            cond.append("status=?")
            params.append(status)
        if role_id:
            cond.append("role_id=?")
            params.append(role_id)
        where = "WHERE " + " AND ".join(cond) if cond else ""
        with get_connection() as conn:
            total = conn.execute(f"SELECT COUNT(*) FROM users {where}", params).fetchone()[0]
            rows = conn.execute(f"""
                SELECT u.*, r.name as role_name
                FROM users u LEFT JOIN roles r ON u.role_id = r.id
                {where}
                ORDER BY u.id DESC LIMIT ? OFFSET ?
            """, params + [per_page, (page-1)*per_page]).fetchall()
            return [dict(row) for row in rows], total

    @staticmethod
    def create_user(username, password, role_id=1):
        if not username or len(password) < 6:
            return False
        salt = _new_salt()
        pwd_hash = _hash_password(password, bytes.fromhex(salt))
        try:
            with get_connection() as conn:
                conn.execute(
                    "INSERT INTO users (username, password_hash, salt, role_id, status, created_at) VALUES (?,?,?,?,?,?)",
                    (username, pwd_hash, salt, role_id, 'active', _now())
                )
            return True
        except sqlite3.IntegrityError:
            return False

    @staticmethod
    def update_user(user_id, username, role_id, status='active', password=None):
        with get_connection() as conn:
            if password and len(password) >= 6:
                salt = _new_salt()
                pwd_hash = _hash_password(password, bytes.fromhex(salt))
                conn.execute(
                    "UPDATE users SET username=?, role_id=?, status=?, password_hash=?, salt=?, last_login=? WHERE id=?",
                    (username, role_id, status, pwd_hash, salt, _now(), user_id)
                )
            else:
                conn.execute(
                    "UPDATE users SET username=?, role_id=?, status=? WHERE id=?",
                    (username, role_id, status, user_id)
                )
        return True

    @staticmethod
    def delete_user(user_id):
        with get_connection() as conn:
            cur = conn.execute("DELETE FROM users WHERE id=?", (user_id,))
            return cur.rowcount > 0

    @staticmethod
    def set_status(user_id, status):
        with get_connection() as conn:
            cur = conn.execute("UPDATE users SET status=? WHERE id=?", (status, user_id))
            return cur.rowcount > 0

    @staticmethod
    def bulk_set_status(user_ids, status):
        if not user_ids: return 0
        placeholders = ','.join(['?']*len(user_ids))
        with get_connection() as conn:
            cur = conn.execute(f"UPDATE users SET status=? WHERE id IN ({placeholders})", [status] + user_ids)
            return cur.rowcount

    @staticmethod
    def bulk_delete(user_ids):
        if not user_ids: return 0
        placeholders = ','.join(['?']*len(user_ids))
        with get_connection() as conn:
            cur = conn.execute(f"DELETE FROM users WHERE id IN ({placeholders})", user_ids)
            return cur.rowcount

    @staticmethod
    def verify_user(username, password, admin_required=False):
        row = UserRepository.get_user_by_username(username)
        if not row or row['status'] != 'active':
            return False
        if admin_required and row['role_code'] != 'admin':
            return False
        salt = bytes.fromhex(row['salt'])
        return _hash_password(password, salt) == row['password_hash']

    @staticmethod
    def mark_login(username):
        with get_connection() as conn:
            conn.execute("UPDATE users SET last_login=? WHERE username=?", (_now(), username))

    @staticmethod
    def ensure_default_admin():
        admin = UserRepository.get_user_by_username(AppConfig.ADMIN_USERNAME)
        if not admin:
            UserRepository.create_user(AppConfig.ADMIN_USERNAME, AppConfig.ADMIN_PASSWORD, role_id=1)
        else:
            # 确保角色为admin
            with get_connection() as conn:
                admin_role = conn.execute("SELECT id FROM roles WHERE code='admin'").fetchone()
                if admin_role:
                    conn.execute("UPDATE users SET role_id=? WHERE username=?", (admin_role[0], AppConfig.ADMIN_USERNAME))
            # 重置密码（若需要）

class DialogueRepository:
    @staticmethod
    def save_history(user_id, username, query, response, response_type='text', source='', meta=None):
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO user_histories (user_id, username, query, response, response_type, source, meta) VALUES (?,?,?,?,?,?,?)",
                (user_id, username, query, response, response_type, source, json.dumps(meta, ensure_ascii=False) if meta is not None else '{}')
            )

    @staticmethod
    def list_history(user_id=None, page=1, per_page=20):
        cond = []
        params = []
        if user_id is not None:
            cond.append("user_id=?")
            params.append(user_id)
        where = "WHERE " + " AND ".join(cond) if cond else ""
        with get_connection() as conn:
            total = conn.execute(f"SELECT COUNT(*) FROM user_histories {where}", params).fetchone()[0]
            rows = conn.execute(f"SELECT * FROM user_histories {where} ORDER BY id DESC LIMIT ? OFFSET ?",
                                params + [per_page, (page-1)*per_page]).fetchall()
            return [dict(row) for row in rows], total

    @staticmethod
    def count_history(user_id=None):
        with get_connection() as conn:
            if user_id is not None:
                row = conn.execute("SELECT COUNT(*) FROM user_histories WHERE user_id=?", (user_id,)).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) FROM user_histories").fetchone()
            return row[0] if row else 0

    @staticmethod
    def report_counts(user_id=None):
        cond = []
        params = []
        if user_id is not None:
            cond.append("user_id=?")
            params.append(user_id)
        where = "WHERE " + " AND ".join(cond) if cond else ""
        with get_connection() as conn:
            rows = conn.execute(f"SELECT response_type, COUNT(*) as count FROM user_histories {where} GROUP BY response_type", params).fetchall()
            return {row['response_type']: row['count'] for row in rows}
