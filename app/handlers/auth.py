from __future__ import annotations
import time
from collections import defaultdict
from app.handlers.base import BaseHandler
from app.models.user import UserRepository
from app.models.db import record_audit
from config import AppConfig


# 简单限速
class RateLimiter:
    _failures = defaultdict(list)
    @classmethod
    def is_limited(cls, ip, username):
        key = f"{ip}:{username}"
        now = time.time()
        cls._failures[key] = [t for t in cls._failures[key] if now - t < 60]
        if len(cls._failures[key]) >= 5:
            return True
        return False
    @classmethod
    def record_failure(cls, ip, username):
        key = f"{ip}:{username}"
        cls._failures[key].append(time.time())
    @classmethod
    def reset(cls, ip, username):
        key = f"{ip}:{username}"
        cls._failures.pop(key, None)

class LoginHandler(BaseHandler):
    def get(self):
        if self.current_user:
            self.redirect("/")
            return
        self.render_page("login.html", error=None)

    def post(self):
        username = self.get_body_argument("username", "").strip()
        password = self.get_body_argument("password", "")
        ip = self.client_ip()
        if RateLimiter.is_limited(ip, username):
            self.render_page("login.html", error="登录尝试过多，请稍后再试")
            return
        if not UserRepository.verify_user(username, password):
            RateLimiter.record_failure(ip, username)
            record_audit("login_failed", username, ip, "密码错误")
            self.render_page("login.html", error="用户名或密码错误")
            return
        RateLimiter.reset(ip, username)
        UserRepository.mark_login(username)
        self.login_user(username)
        record_audit("login_success", username, ip, "登录成功")
        self.redirect("/")

class RegisterHandler(BaseHandler):
    def get(self):
        self.render_page("register.html", error=None)

    def post(self):
        username = self.get_body_argument("username", "").strip()
        password = self.get_body_argument("password", "")
        confirm = self.get_body_argument("confirm", "")
        if password != confirm:
            self.render_page("register.html", error="密码不一致")
            return
        # 默认角色 user (id=2)
        if not UserRepository.create_user(username, password, role_id=2):
            self.render_page("register.html", error="注册失败，用户名可能已存在")
            return
        record_audit("register", username, self.client_ip(), "注册成功")
        self.login_user(username)
        self.redirect("/")

class LogoutHandler(BaseHandler):
    def get(self):
        self.logout_user()
        self.redirect("/login")

class AdminLoginHandler(BaseHandler):
    def get(self):
        if self.current_user and self.current_user.get('role_code') == 'admin':
            self.redirect("/admin")
            return
        self.render_page("admin/login.html", error=None)

    def post(self):
        username = self.get_body_argument("username", "").strip()
        password = self.get_body_argument("password", "")
        ip = self.client_ip()
        if RateLimiter.is_limited(ip, username):
            self.render_page("admin/login.html", error="登录尝试过多")
            return
        if not UserRepository.verify_user(username, password, admin_required=True):
            RateLimiter.record_failure(ip, username)
            record_audit("admin_login_failed", username, ip, "后台登录失败")
            self.render_page("admin/login.html", error="管理员账号或密码错误")
            return
        RateLimiter.reset(ip, username)
        UserRepository.mark_login(username)
        self.login_user(username)
        record_audit("admin_login_success", username, ip, "后台登录成功")
        self.redirect("/admin")

class AdminLogoutHandler(BaseHandler):
    def get(self):
        self.logout_user()
        self.redirect("/admin/login")