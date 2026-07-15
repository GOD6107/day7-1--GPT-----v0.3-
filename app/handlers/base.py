from __future__ import annotations
import tornado.web
from app.models.user import UserRepository
from app.models.rbac import MenuRepository
from config import AppConfig

class BaseHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Server", "MiniDataFinder")

    def get_current_user(self):
        username = self.get_secure_cookie(AppConfig.SESSION_COOKIE_NAME)
        if not username:
            return None
        user = UserRepository.get_user_by_username(username.decode())
        if not user or user['status'] != 'active':
            self.clear_cookie(AppConfig.SESSION_COOKIE_NAME)
            return None
        return dict(user)

    def login_user(self, username):
        self.set_secure_cookie(AppConfig.SESSION_COOKIE_NAME, username, expires_days=AppConfig.SESSION_EXPIRES_DAYS)

    def logout_user(self):
        self.clear_cookie(AppConfig.SESSION_COOKIE_NAME)

    def client_ip(self):
        return self.request.headers.get("X-Forwarded-For", self.request.remote_ip).split(',')[0].strip()

    def render_page(self, template_name, **kwargs):
        kwargs.setdefault('current_user', self.current_user)
        kwargs.setdefault('project_name', AppConfig.PROJECT_NAME)
        kwargs.setdefault('version', AppConfig.VERSION)
        self.render(template_name, **kwargs)

class AdminBaseHandler(BaseHandler):
    def require_admin(self):
        if not self.current_user:
            self.redirect("/admin/login")
            return False
        if self.current_user.get('role_code') != 'admin':
            self.set_status(403)
            self.write("管理员权限不足")
            return False
        return True

    def render_page(self, template_name, **kwargs):
        kwargs.setdefault('sidebar_menu', MenuRepository.get_menu_tree(self.current_user['role_id']) if self.current_user else [])
        kwargs.setdefault('current_role', self.current_user.get('role_name') if self.current_user else '')
        super().render_page(template_name, **kwargs)