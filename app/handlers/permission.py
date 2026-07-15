# app/handlers/permission.py
from app.handlers.base import AdminBaseHandler
from app.models.user import UserRepository
from app.models.rbac import RoleRepository, FunctionRepository, MenuRepository
from app.models.db import record_audit
import json

# ---------- 用户管理 ----------
class AdminUserHandler(AdminBaseHandler):
    def get(self):
        if not self.require_admin(): return
        page = int(self.get_argument("page", 1))
        keyword = self.get_argument("keyword", "")
        status = self.get_argument("status", "")
        role_id = self.get_argument("role_id", None)
        users, total = UserRepository.list_users(keyword, status, role_id, page)
        roles = RoleRepository.list_roles()[0]  # 所有角色用于下拉
        pages = (total + 19) // 20
        self.render_page("admin/users.html", users=users, total=total, page=page, pages=pages,
                         keyword=keyword, status=status, role_id=role_id, roles=roles,
                         msg=self.get_argument("msg",""), msg_type=self.get_argument("msg_type",""))

class AdminUserCreateHandler(AdminBaseHandler):
    def post(self):
        if not self.require_admin(): return
        username = self.get_body_argument("username", "").strip()
        password = self.get_body_argument("password", "")
        role_id = int(self.get_body_argument("role_id", 1))
        ok = UserRepository.create_user(username, password, role_id)
        record_audit("user_create", self.current_user['username'], self.client_ip(), username)
        self.redirect(f"/admin/users?msg={'创建成功' if ok else '创建失败'}&msg_type={'success' if ok else 'error'}")

class AdminUserEditHandler(AdminBaseHandler):
    def post(self, user_id):
        if not self.require_admin(): return
        user_id = int(user_id)
        username = self.get_body_argument("username", "").strip()
        role_id = int(self.get_body_argument("role_id", 1))
        status = self.get_body_argument("status", "active")
        password = self.get_body_argument("password", "")
        ok = UserRepository.update_user(user_id, username, role_id, status, password if password else None)
        record_audit("user_edit", self.current_user['username'], self.client_ip(), f"id={user_id}")
        self.redirect(f"/admin/users?msg={'修改成功' if ok else '修改失败'}&msg_type={'success' if ok else 'error'}")

class AdminUserDeleteHandler(AdminBaseHandler):
    def post(self, user_id):
        if not self.require_admin(): return
        user_id = int(user_id)
        user = UserRepository.get_user_by_id(user_id)
        if user and user['username'] == 'admin':
            self.redirect("/admin/users?msg=不能删除管理员&msg_type=error")
            return
        ok = UserRepository.delete_user(user_id)
        record_audit("user_delete", self.current_user['username'], self.client_ip(), f"id={user_id}")
        self.redirect(f"/admin/users?msg={'删除成功' if ok else '删除失败'}&msg_type={'success' if ok else 'error'}")

class AdminUserStatusHandler(AdminBaseHandler):
    def post(self, user_id):
        if not self.require_admin(): return
        user_id = int(user_id)
        status = self.get_body_argument("status", "active")
        ok = UserRepository.set_status(user_id, status)
        record_audit("user_status", self.current_user['username'], self.client_ip(), f"id={user_id},status={status}")
        self.redirect(f"/admin/users?msg={'状态更新成功' if ok else '更新失败'}&msg_type={'success' if ok else 'error'}")

class AdminUserBulkHandler(AdminBaseHandler):
    def post(self):
        if not self.require_admin(): return
        ids = [int(x) for x in self.get_body_arguments("ids") if x.isdigit()]
        # 过滤掉 admin
        admin = UserRepository.get_user_by_username('admin')
        if admin:
            ids = [i for i in ids if i != admin['id']]
        if not ids:
            self.redirect("/admin/users?msg=未选择有效用户&msg_type=error")
            return
        action = self.get_body_argument("action", "")
        if action == "delete":
            count = UserRepository.bulk_delete(ids)
            msg = f"已删除 {count} 个用户"
        elif action == "enable":
            count = UserRepository.bulk_set_status(ids, "active")
            msg = f"已启用 {count} 个用户"
        elif action == "disable":
            count = UserRepository.bulk_set_status(ids, "disabled")
            msg = f"已禁用 {count} 个用户"
        else:
            self.redirect("/admin/users?msg=无效操作&msg_type=error")
            return
        record_audit("user_bulk", self.current_user['username'], self.client_ip(), f"{action}: {count}")
        self.redirect(f"/admin/users?msg={msg}&msg_type=success")

# ---------- 角色管理 ----------
class AdminRoleHandler(AdminBaseHandler):
    def get(self):
        if not self.require_admin(): return
        page = int(self.get_argument("page", 1))
        keyword = self.get_argument("keyword", "")
        status = self.get_argument("status", "")
        roles, total = RoleRepository.list_roles(keyword, status, page)
        pages = (total + 19) // 20
        # 获取功能树
        function_tree = FunctionRepository.get_tree()
        # 获取每个角色的权限ID
        perm_ids = {}
        for role in roles:
            perm_ids[role['id']] = set(RoleRepository.get_role_permission_ids(role['id']))
        self.render_page("admin/roles.html", roles=roles, total=total, page=page, pages=pages,
                         keyword=keyword, status=status, function_tree=function_tree,
                         permission_ids=perm_ids,
                         msg=self.get_argument("msg",""), msg_type=self.get_argument("msg_type",""))

class AdminRoleCreateHandler(AdminBaseHandler):
    def post(self):
        if not self.require_admin(): return
        code = self.get_body_argument("code", "").strip()
        name = self.get_body_argument("name", "").strip()
        description = self.get_body_argument("description", "").strip()
        function_ids = [int(x) for x in self.get_body_arguments("function_ids") if x.isdigit()]
        ok = RoleRepository.create_role(code, name, description, function_ids)
        record_audit("role_create", self.current_user['username'], self.client_ip(), code)
        self.redirect(f"/admin/roles?msg={'创建成功' if ok else '创建失败'}&msg_type={'success' if ok else 'error'}")

class AdminRoleEditHandler(AdminBaseHandler):
    def post(self, role_id):
        if not self.require_admin(): return
        role_id = int(role_id)
        code = self.get_body_argument("code", "").strip()
        name = self.get_body_argument("name", "").strip()
        description = self.get_body_argument("description", "").strip()
        function_ids = [int(x) for x in self.get_body_arguments("function_ids") if x.isdigit()]
        ok = RoleRepository.update_role(role_id, code, name, description, function_ids)
        record_audit("role_edit", self.current_user['username'], self.client_ip(), f"id={role_id}")
        self.redirect(f"/admin/roles?msg={'修改成功' if ok else '修改失败'}&msg_type={'success' if ok else 'error'}")

class AdminRoleDeleteHandler(AdminBaseHandler):
    def post(self, role_id):
        if not self.require_admin(): return
        role_id = int(role_id)
        ok, msg = RoleRepository.delete_role(role_id)
        record_audit("role_delete", self.current_user['username'], self.client_ip(), f"id={role_id}")
        self.redirect(f"/admin/roles?msg={msg}&msg_type={'success' if ok else 'error'}")

class AdminRoleStatusHandler(AdminBaseHandler):
    def post(self, role_id):
        if not self.require_admin(): return
        role_id = int(role_id)
        status = self.get_body_argument("status", "active")
        ok = RoleRepository.toggle_status(role_id, status)
        record_audit("role_status", self.current_user['username'], self.client_ip(), f"id={role_id},status={status}")
        self.redirect(f"/admin/roles?msg={'状态更新成功' if ok else '更新失败'}&msg_type={'success' if ok else 'error'}")

# ---------- 功能管理 ----------
class AdminFunctionHandler(AdminBaseHandler):
    def get(self):
        if not self.require_admin(): return
        page = int(self.get_argument("page", 1))
        keyword = self.get_argument("keyword", "")
        status = self.get_argument("status", "")
        functions, total = FunctionRepository.list_functions(keyword, status, page)
        pages = (total + 19) // 20
        parent_choices = FunctionRepository.list_parent_choices()
        self.render_page("admin/functions.html", functions=functions, total=total, page=page, pages=pages,
                         keyword=keyword, status=status, parent_choices=parent_choices,
                         msg=self.get_argument("msg",""), msg_type=self.get_argument("msg_type",""))

class AdminFunctionCreateHandler(AdminBaseHandler):
    def post(self):
        if not self.require_admin(): return
        code = self.get_body_argument("code", "").strip()
        name = self.get_body_argument("name", "").strip()
        route = self.get_body_argument("route", "").strip()
        parent_id = int(self.get_body_argument("parent_id", 0))
        sort_order = int(self.get_body_argument("sort_order", 0))
        status = self.get_body_argument("status", "active")
        ok = FunctionRepository.create_function(code, parent_id, name, route, sort_order, status)
        record_audit("func_create", self.current_user['username'], self.client_ip(), code)
        self.redirect(f"/admin/functions?msg={'创建成功' if ok else '创建失败'}&msg_type={'success' if ok else 'error'}")

class AdminFunctionEditHandler(AdminBaseHandler):
    def post(self, func_id):
        if not self.require_admin(): return
        func_id = int(func_id)
        code = self.get_body_argument("code", "").strip()
        name = self.get_body_argument("name", "").strip()
        route = self.get_body_argument("route", "").strip()
        parent_id = int(self.get_body_argument("parent_id", 0))
        sort_order = int(self.get_body_argument("sort_order", 0))
        status = self.get_body_argument("status", "active")
        ok = FunctionRepository.update_function(func_id, code, parent_id, name, route, sort_order, status)
        record_audit("func_edit", self.current_user['username'], self.client_ip(), f"id={func_id}")
        self.redirect(f"/admin/functions?msg={'修改成功' if ok else '修改失败'}&msg_type={'success' if ok else 'error'}")

class AdminFunctionDeleteHandler(AdminBaseHandler):
    def post(self, func_id):
        if not self.require_admin(): return
        func_id = int(func_id)
        ok, msg = FunctionRepository.delete_function(func_id)
        record_audit("func_delete", self.current_user['username'], self.client_ip(), f"id={func_id}")
        self.redirect(f"/admin/functions?msg={msg}&msg_type={'success' if ok else 'error'}")

class AdminFunctionStatusHandler(AdminBaseHandler):
    def post(self, func_id):
        if not self.require_admin(): return
        func_id = int(func_id)
        status = self.get_body_argument("status", "active")
        ok = FunctionRepository.toggle_status(func_id, status)
        record_audit("func_status", self.current_user['username'], self.client_ip(), f"id={func_id},status={status}")
        self.redirect(f"/admin/functions?msg={'状态更新成功' if ok else '更新失败'}&msg_type={'success' if ok else 'error'}")

# ---------- 菜单管理 ----------
class AdminMenuHandler(AdminBaseHandler):
    def get(self):
        if not self.require_admin(): return
        roles = RoleRepository.list_roles()[0]
        selected_role_id = int(self.get_argument("role_id", roles[0]['id'] if roles else 0))
        # 获取菜单树
        menu_tree = MenuRepository.get_menu_tree(selected_role_id)
        # 获取排序列表
        menu_rows = MenuRepository.get_menu_rows(selected_role_id)
        self.render_page("admin/menus.html", roles=roles, selected_role_id=selected_role_id,
                         menu_tree=menu_tree, menu_rows=menu_rows,
                         msg=self.get_argument("msg",""), msg_type=self.get_argument("msg_type",""))

class AdminMenuMoveHandler(AdminBaseHandler):
    def post(self):
        if not self.require_admin(): return
        role_id = int(self.get_body_argument("role_id", 0))
        function_id = int(self.get_body_argument("function_id", 0))
        direction = self.get_body_argument("direction", "")
        ok, msg = MenuRepository.move_menu_item(role_id, function_id, direction)
        record_audit("menu_move", self.current_user['username'], self.client_ip(), f"role={role_id},func={function_id},dir={direction}")
        self.redirect(f"/admin/menus?msg={msg}&msg_type={'success' if ok else 'error'}&role_id={role_id}")