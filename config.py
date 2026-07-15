from __future__ import annotations
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

class AppConfig:
    PROJECT_NAME = "MiniDataFinder"
    VERSION = "v0.3"
    HOST = "127.0.0.1"
    PORT = 10010
    DEBUG = False

    TEMPLATE_DIR = PROJECT_ROOT / "app" / "templates"
    STATIC_DIR = PROJECT_ROOT / "app" / "static"
    DATABASE_PATH = PROJECT_ROOT / "database" / "mini.db"

    COOKIE_SECRET = "mini-secret-change-in-production"
    SESSION_COOKIE_NAME = "mini_user"
    SESSION_EXPIRES_DAYS = 1
    COOKIE_SECURE = False
    COOKIE_SAMESITE = "Lax"

    LOGIN_URL = "/login"
    ADMIN_LOGIN_URL = "/admin/login"

    ADMIN_USERNAME = "admin"
    ADMIN_PASSWORD = "admin123"

    LOGIN_RATE_LIMIT_WINDOW = 60
    LOGIN_RATE_LIMIT_MAX = 5
    COLLECTOR_TIMEOUT_SECONDS = 8
    COLLECTOR_MAX_RESPONSE_BYTES = 1024 * 1024
    ALLOW_PRIVATE_SOURCE_URLS = False