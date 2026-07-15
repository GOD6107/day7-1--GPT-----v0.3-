from app.handlers.base import AdminBaseHandler
from app.models.user import UserRepository
from app.models.rbac import RoleRepository, FunctionRepository
from app.models.db import get_connection

class AdminIndexHandler(AdminBaseHandler):
    def get(self):
        if not self.require_admin():
            return
        metrics = [
            ("用户数", UserRepository.list_users()[1]),
            ("角色数", RoleRepository.list_roles()[1]),
            ("功能数", FunctionRepository.list_functions()[1]),
        ]
        # 获取最近审计日志
        with get_connection() as conn:
            logs = [dict(row) for row in conn.execute(
                "SELECT username, action, ip, detail, created_at FROM audit_logs ORDER BY id DESC LIMIT 8"
            ).fetchall()]
        self.render_page("admin/index.html", metrics=metrics, logs=logs)