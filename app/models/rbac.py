from __future__ import annotations
import sqlite3
from app.models.db import get_connection

_HIDDEN_FUNCTION_CODES = {'permission', 'watch', 'model'}

class RoleRepository:
    @staticmethod
    def list_roles(keyword='', status='', page=1, per_page=20):
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
            total = conn.execute(f"SELECT COUNT(*) FROM roles {where}", params).fetchone()[0]
            rows = conn.execute(f"""
                SELECT r.*, COUNT(DISTINCT u.id) as user_count,
                       COUNT(DISTINCT rf.function_id) as func_count
                FROM roles r
                LEFT JOIN users u ON u.role_id = r.id
                LEFT JOIN role_function_map rf ON rf.role_id = r.id
                {where}
                GROUP BY r.id
                ORDER BY r.is_system DESC, r.id
                LIMIT ? OFFSET ?
            """, params + [per_page, (page-1)*per_page]).fetchall()
            return [dict(row) for row in rows], total

    @staticmethod
    def get_role(role_id):
        with get_connection() as conn:
            return conn.execute("SELECT * FROM roles WHERE id=?", (role_id,)).fetchone()

    @staticmethod
    def get_role_by_code(code):
        with get_connection() as conn:
            return conn.execute("SELECT * FROM roles WHERE code=?", (code,)).fetchone()

    @staticmethod
    def create_role(code, name, description='', function_ids=None):
        try:
            with get_connection() as conn:
                conn.execute("INSERT INTO roles (code, name, description, is_system, status) VALUES (?,?,?,0,'active')",
                             (code, name, description))
                role_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                if function_ids:
                    for idx, fid in enumerate(function_ids, 1):
                        conn.execute("INSERT INTO role_function_map (role_id, function_id, sort_order) VALUES (?,?,?)",
                                     (role_id, fid, idx))
            return True
        except sqlite3.IntegrityError:
            return False

    @staticmethod
    def update_role(role_id, code, name, description, function_ids=None):
        role = RoleRepository.get_role(role_id)
        if not role or role['is_system']:
            return False
        with get_connection() as conn:
            conn.execute("UPDATE roles SET code=?, name=?, description=? WHERE id=?", (code, name, description, role_id))
            if function_ids is not None:
                conn.execute("DELETE FROM role_function_map WHERE role_id=?", (role_id,))
                for idx, fid in enumerate(function_ids, 1):
                    conn.execute("INSERT INTO role_function_map (role_id, function_id, sort_order) VALUES (?,?,?)",
                                 (role_id, fid, idx))
        return True

    @staticmethod
    def delete_role(role_id):
        role = RoleRepository.get_role(role_id)
        if not role or role['is_system']:
            return False, "系统角色不可删除"
        with get_connection() as conn:
            cnt = conn.execute("SELECT COUNT(*) FROM users WHERE role_id=?", (role_id,)).fetchone()[0]
            if cnt > 0:
                return False, "该角色下还有用户"
            conn.execute("DELETE FROM role_function_map WHERE role_id=?", (role_id,))
            conn.execute("DELETE FROM roles WHERE id=?", (role_id,))
        return True, "删除成功"

    @staticmethod
    def toggle_status(role_id, status):
        role = RoleRepository.get_role(role_id)
        if not role or role['is_system']:
            return False
        with get_connection() as conn:
            conn.execute("UPDATE roles SET status=? WHERE id=?", (status, role_id))
        return True

    @staticmethod
    def get_role_permission_ids(role_id):
        with get_connection() as conn:
            rows = conn.execute("SELECT function_id FROM role_function_map WHERE role_id=? ORDER BY sort_order", (role_id,)).fetchall()
            return [row[0] for row in rows]

class FunctionRepository:
    @staticmethod
    def list_functions(keyword='', status='', page=1, per_page=20):
        cond = ["f.code NOT IN ('permission','watch','model')"]
        params = []
        if keyword:
            cond.append("(f.code LIKE ? OR f.name LIKE ?)")
            params.extend([f"%{keyword}%", f"%{keyword}%"])
        if status:
            cond.append("f.status=?")
            params.append(status)
        where = "WHERE " + " AND ".join(cond)
        with get_connection() as conn:
            total = conn.execute(f"SELECT COUNT(*) FROM functions f {where}", params).fetchone()[0]
            rows = conn.execute(f"""
                SELECT f.*, CASE WHEN p.code IN ('permission','watch','model') THEN '' ELSE p.name END as parent_name
                FROM functions f
                LEFT JOIN functions p ON p.id = f.parent_id
                {where}
                ORDER BY f.parent_id, f.sort_order
                LIMIT ? OFFSET ?
            """, params + [per_page, (page-1)*per_page]).fetchall()
            return [dict(row) for row in rows], total

    @staticmethod
    def create_function(code, parent_id, name, route, sort_order=0, status='active'):
        try:
            with get_connection() as conn:
                conn.execute(
                    "INSERT INTO functions (code, parent_id, name, route, sort_order, status) VALUES (?,?,?,?,?,?)",
                    (code, parent_id, name, route, sort_order, status)
                )
            return True
        except sqlite3.IntegrityError:
            return False

    @staticmethod
    def update_function(func_id, code, parent_id, name, route, sort_order, status):
        try:
            with get_connection() as conn:
                conn.execute(
                    "UPDATE functions SET code=?, parent_id=?, name=?, route=?, sort_order=?, status=? WHERE id=?",
                    (code, parent_id, name, route, sort_order, status, func_id)
                )
            return True
        except sqlite3.IntegrityError:
            return False

    @staticmethod
    def delete_function(func_id):
        with get_connection() as conn:
            cnt = conn.execute("SELECT COUNT(*) FROM functions WHERE parent_id=?", (func_id,)).fetchone()[0]
            if cnt > 0:
                return False, "存在子功能"
            conn.execute("DELETE FROM role_function_map WHERE function_id=?", (func_id,))
            conn.execute("DELETE FROM functions WHERE id=?", (func_id,))
        return True, "删除成功"

    @staticmethod
    def toggle_status(func_id, status):
        with get_connection() as conn:
            conn.execute("UPDATE functions SET status=? WHERE id=?", (status, func_id))
        return True

    @staticmethod
    def get_tree(include_disabled=False, selected_ids=None):
        with get_connection() as conn:
            rows = conn.execute("SELECT * FROM functions ORDER BY parent_id, sort_order").fetchall()
        rows = [row for row in rows if row['code'] not in _HIDDEN_FUNCTION_CODES]
        nodes = {}
        for row in rows:
            d = dict(row)
            d['children'] = []
            nodes[d['id']] = d
        roots = []
        for node in nodes.values():
            if node['parent_id'] == 0:
                roots.append(node)
            else:
                parent = nodes.get(node['parent_id'])
                if parent:
                    parent['children'].append(node)
                else:
                    roots.append(node)
        def sort_tree(items):
            items.sort(key=lambda x: x['sort_order'])
            for item in items:
                sort_tree(item['children'])
        sort_tree(roots)
        return roots

    # ---------- 新增方法 ----------
    @staticmethod
    def list_parent_choices():
        """返回所有功能的 id 和 name，用于父级下拉选择"""
        with get_connection() as conn:
            rows = conn.execute("SELECT id, name FROM functions WHERE code NOT IN ('permission','watch','model') ORDER BY parent_id, sort_order").fetchall()
            return [dict(row) for row in rows]

class MenuRepository:
    @staticmethod
    def get_menu_tree(role_id):
        func_ids = RoleRepository.get_role_permission_ids(role_id)
        with get_connection() as conn:
            rows = conn.execute("SELECT * FROM functions WHERE status='active' AND code NOT IN ('permission','watch','model')").fetchall()
        all_funcs = {row['id']: dict(row) for row in rows}
        def build(node):
            children = []
            for child in all_funcs.values():
                if child['parent_id'] == node['id'] and child['id'] in func_ids:
                    child['children'] = build(child)
                    children.append(child)
            return children
        roots = []
        for func in all_funcs.values():
            if func['parent_id'] == 0 and func['id'] in func_ids:
                func['children'] = build(func)
                roots.append(func)
            elif func['parent_id'] != 0 and func['id'] in func_ids and func['parent_id'] not in all_funcs:
                func['children'] = build(func)
                roots.append(func)
        roots.sort(key=lambda x: x['sort_order'])
        return roots

    # ---------- 新增方法 ----------
    @staticmethod
    def get_menu_rows(role_id):
        """获取指定角色下所有菜单项的排序列表，包含 function_id, name, menu_sort_order"""
        with get_connection() as conn:
            rows = conn.execute("""
                SELECT f.id as function_id, f.name, rf.sort_order as menu_sort_order
                FROM functions f
                JOIN role_function_map rf ON rf.function_id = f.id
                WHERE rf.role_id = ? AND f.code NOT IN ('permission','watch','model')
                ORDER BY rf.sort_order
            """, (role_id,)).fetchall()
            return [dict(row) for row in rows]

    @staticmethod
    def move_menu_item(role_id, function_id, direction):
        """移动菜单项排序（上/下）"""
        with get_connection() as conn:
            # 获取当前排序值
            row = conn.execute("SELECT sort_order FROM role_function_map WHERE role_id=? AND function_id=?", (role_id, function_id)).fetchone()
            if not row:
                return False, "菜单项不存在"
            current_sort = row[0]
            if direction == 'up':
                target_sort = current_sort - 1
            elif direction == 'down':
                target_sort = current_sort + 1
            else:
                return False, "无效方向"
            # 查找目标排序的 function_id
            target_row = conn.execute("SELECT function_id FROM role_function_map WHERE role_id=? AND sort_order=?", (role_id, target_sort)).fetchone()
            if not target_row:
                return False, "边界外"
            target_func = target_row[0]
            # 交换排序值
            conn.execute("UPDATE role_function_map SET sort_order=? WHERE role_id=? AND function_id=?", (target_sort, role_id, function_id))
            conn.execute("UPDATE role_function_map SET sort_order=? WHERE role_id=? AND function_id=?", (current_sort, role_id, target_func))
            return True, "移动成功"