from __future__ import annotations
import json
import sqlite3
from app.models.db import get_connection

class ModelRepository:
    @staticmethod
    def list_models(keyword='', status='', page=1, per_page=6):
        cond = []
        params = []
        if keyword:
            cond.append("(code LIKE ? OR name LIKE ?)")
            params.extend([f"%{keyword}%", f"%{keyword}%"])
        if status:
            cond.append("status=?")
            params.append(status)
        where = "WHERE " + " AND ".join(cond) if cond else ""
        with get_connection() as conn:
            total = conn.execute(f"SELECT COUNT(*) FROM model_engines {where}", params).fetchone()[0]
            rows = conn.execute(f"SELECT * FROM model_engines {where} ORDER BY is_default DESC, id DESC LIMIT ? OFFSET ?",
                                params + [per_page, (page-1)*per_page]).fetchall()
            return [dict(row) for row in rows], total

    @staticmethod
    def get_model(model_id):
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM model_engines WHERE id=?", (model_id,)).fetchone()
            return dict(row) if row else None

    @staticmethod
    def get_default_model():
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM model_engines WHERE is_default=1 AND status='active'").fetchone()
            if not row:
                row = conn.execute("SELECT * FROM model_engines WHERE status='active' ORDER BY id LIMIT 1").fetchone()
            return dict(row) if row else None

    @staticmethod
    def create_model(data):
        try:
            with get_connection() as conn:
                if data.get('is_default', 0):
                    conn.execute("UPDATE model_engines SET is_default=0")
                conn.execute("""
                    INSERT INTO model_engines (code, name, provider, base_url, api_key, model_name, category,
                    system_prompt, top_value, context_count, is_default, status)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """, (data['code'], data['name'], data.get('provider',''), data.get('base_url',''),
                      data.get('api_key',''), data.get('model_name',''), data.get('category','text'),
                      data.get('system_prompt',''), data.get('top_value',0.8), data.get('context_count',8),
                      data.get('is_default',0), data.get('status','active')))
            return True
        except:
            return False

    @staticmethod
    def update_model(model_id, data):
        try:
            with get_connection() as conn:
                if data.get('is_default', 0):
                    conn.execute("UPDATE model_engines SET is_default=0 WHERE id!=?", (model_id,))
                conn.execute("""
                    UPDATE model_engines SET code=?, name=?, provider=?, base_url=?, api_key=?, model_name=?,
                    category=?, system_prompt=?, top_value=?, context_count=?, is_default=?, status=?
                    WHERE id=?
                """, (data['code'], data['name'], data.get('provider',''), data.get('base_url',''),
                      data.get('api_key',''), data.get('model_name',''), data.get('category','text'),
                      data.get('system_prompt',''), data.get('top_value',0.8), data.get('context_count',8),
                      data.get('is_default',0), data.get('status','active'), model_id))
            return True
        except:
            return False

    @staticmethod
    def delete_model(model_id):
        with get_connection() as conn:
            cur = conn.execute("DELETE FROM model_engines WHERE id=?", (model_id,))
            # 如果删除了默认，重新设置
            row = conn.execute("SELECT COUNT(*) FROM model_engines WHERE is_default=1").fetchone()[0]
            if row == 0:
                next_row = conn.execute("SELECT id FROM model_engines WHERE status='active' ORDER BY id LIMIT 1").fetchone()
                if next_row:
                    conn.execute("UPDATE model_engines SET is_default=1 WHERE id=?", (next_row[0],))
            return cur.rowcount > 0

    @staticmethod
    def set_default(model_id):
        with get_connection() as conn:
            row = conn.execute("SELECT status FROM model_engines WHERE id=?", (model_id,)).fetchone()
            if not row or row[0] != 'active':
                return False
            conn.execute("UPDATE model_engines SET is_default=0")
            conn.execute("UPDATE model_engines SET is_default=1 WHERE id=?", (model_id,))
        return True

    @staticmethod
    def set_status(model_id, status):
        with get_connection() as conn:
            conn.execute("UPDATE model_engines SET status=? WHERE id=?", (status, model_id))
            # 如果禁用的是默认，重新分配
            if status != 'active':
                row = conn.execute("SELECT is_default FROM model_engines WHERE id=?", (model_id,)).fetchone()
                if row and row[0] == 1:
                    conn.execute("UPDATE model_engines SET is_default=0 WHERE id=?", (model_id,))
                    next_row = conn.execute("SELECT id FROM model_engines WHERE status='active' ORDER BY id LIMIT 1").fetchone()
                    if next_row:
                        conn.execute("UPDATE model_engines SET is_default=1 WHERE id=?", (next_row[0],))
        return True

    @staticmethod
    def add_token_usage(model_id, prompt, completion):
        with get_connection() as conn:
            conn.execute("""
                UPDATE model_engines SET token_prompt=token_prompt+?, token_completion=token_completion+?,
                token_total=token_total+?, last_used_at=datetime('now','localtime')
                WHERE id=?
            """, (prompt, completion, prompt+completion, model_id))