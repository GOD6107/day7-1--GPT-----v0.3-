# coding: utf-8
from __future__ import annotations

import logging
import tornado.ioloop
import tornado.web
from tornado.httpserver import HTTPServer

from app.handlers.auth import LoginHandler, RegisterHandler, LogoutHandler, AdminLoginHandler, AdminLogoutHandler
from app.handlers.home import IndexHandler
from app.handlers.front import (
    ChatHandler, ChatSendHandler,
    WorkerHandler, WorkerSendHandler,
    HistoryHandler, ReportHandler, ReportExportHandler,
)
from app.handlers.admin import AdminIndexHandler
from app.handlers.permission import (
    AdminUserHandler, AdminUserCreateHandler, AdminUserEditHandler, AdminUserDeleteHandler,
    AdminUserStatusHandler, AdminUserBulkHandler,
    AdminRoleHandler, AdminRoleCreateHandler, AdminRoleEditHandler, AdminRoleDeleteHandler,
    AdminRoleStatusHandler,
    AdminFunctionHandler, AdminFunctionCreateHandler, AdminFunctionEditHandler,
    AdminFunctionDeleteHandler, AdminFunctionStatusHandler,
    AdminMenuHandler, AdminMenuMoveHandler,
)
from app.handlers.watch import (
    AdminWatchHandler, AdminWatchSaveHandler,
    AdminSourceHandler, AdminSourceCreateHandler, AdminSourceEditHandler,
    AdminSourceDeleteHandler, AdminSourceToggleHandler, AdminSourceTestHandler,
    AdminWarehouseHandler, AdminWarehouseDeleteHandler, AdminWarehouseBulkHandler,
)
from app.handlers.model_engine import (
    AdminModelHandler, AdminModelCreateHandler, AdminModelEditHandler,
    AdminModelDeleteHandler, AdminModelDefaultHandler, AdminModelStatusHandler,
    AdminModelStreamHandler,
)
from app.models.db import init_db
from app.models.user import UserRepository
from config import AppConfig


def webapp():
    init_db()
    UserRepository.ensure_default_admin()

    settings = {
        "template_path": str(AppConfig.TEMPLATE_DIR),
        "static_path": str(AppConfig.STATIC_DIR),
        "cookie_secret": AppConfig.COOKIE_SECRET,
        "login_url": AppConfig.LOGIN_URL,
        "xsrf_cookies": True,
        "debug": AppConfig.DEBUG,
        "autoreload": AppConfig.DEBUG,
    }

    routes = [
        (r"/", IndexHandler),
        (r"/chat", ChatHandler),
        (r"/chat/send", ChatSendHandler),
        (r"/worker", WorkerHandler),
        (r"/worker/send", WorkerSendHandler),
        (r"/history", HistoryHandler),
        (r"/report", ReportHandler),
        (r"/report/export", ReportExportHandler),
        (r"/login", LoginHandler),
        (r"/register", RegisterHandler),
        (r"/logout", LogoutHandler),
        (r"/admin", AdminIndexHandler),
        (r"/admin/login", AdminLoginHandler),
        (r"/admin/logout", AdminLogoutHandler),
        # 用户管理
        (r"/admin/users", AdminUserHandler),
        (r"/admin/users/create", AdminUserCreateHandler),
        (r"/admin/users/edit/([0-9]+)", AdminUserEditHandler),
        (r"/admin/users/delete/([0-9]+)", AdminUserDeleteHandler),
        (r"/admin/users/status/([0-9]+)", AdminUserStatusHandler),
        (r"/admin/users/bulk", AdminUserBulkHandler),
        # 角色管理
        (r"/admin/roles", AdminRoleHandler),
        (r"/admin/roles/create", AdminRoleCreateHandler),
        (r"/admin/roles/edit/([0-9]+)", AdminRoleEditHandler),
        (r"/admin/roles/delete/([0-9]+)", AdminRoleDeleteHandler),
        (r"/admin/roles/status/([0-9]+)", AdminRoleStatusHandler),
        # 功能管理
        (r"/admin/functions", AdminFunctionHandler),
        (r"/admin/functions/create", AdminFunctionCreateHandler),
        (r"/admin/functions/edit/([0-9]+)", AdminFunctionEditHandler),
        (r"/admin/functions/delete/([0-9]+)", AdminFunctionDeleteHandler),
        (r"/admin/functions/status/([0-9]+)", AdminFunctionStatusHandler),
        # 菜单管理
        (r"/admin/menus", AdminMenuHandler),
        (r"/admin/menus/move", AdminMenuMoveHandler),
        # 瞭望
        (r"/admin/watch", AdminWatchHandler),
        (r"/admin/watch/save", AdminWatchSaveHandler),
        (r"/admin/sources", AdminSourceHandler),
        (r"/admin/sources/create", AdminSourceCreateHandler),
        (r"/admin/sources/edit/([0-9]+)", AdminSourceEditHandler),
        (r"/admin/sources/delete/([0-9]+)", AdminSourceDeleteHandler),
        (r"/admin/sources/toggle/([0-9]+)", AdminSourceToggleHandler),
        (r"/admin/sources/test/([0-9]+)", AdminSourceTestHandler),
        (r"/admin/warehouse", AdminWarehouseHandler),
        (r"/admin/warehouse/delete/([0-9]+)", AdminWarehouseDeleteHandler),
        (r"/admin/warehouse/bulk", AdminWarehouseBulkHandler),
        # 模型引擎
        (r"/admin/models", AdminModelHandler),
        (r"/admin/models/create", AdminModelCreateHandler),
        (r"/admin/models/edit/([0-9]+)", AdminModelEditHandler),
        (r"/admin/models/delete/([0-9]+)", AdminModelDeleteHandler),
        (r"/admin/models/default/([0-9]+)", AdminModelDefaultHandler),
        (r"/admin/models/status/([0-9]+)", AdminModelStatusHandler),
        (r"/admin/models/stream/([0-9]+)", AdminModelStreamHandler),
    ]
    return tornado.web.Application(routes, **settings)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app = webapp()
    server = HTTPServer(app)
    server.listen(AppConfig.PORT, address=AppConfig.HOST)
    print(f"Server started at http://{AppConfig.HOST}:{AppConfig.PORT}")
    tornado.ioloop.IOLoop.current().start()