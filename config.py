import os
from datetime import timedelta
from secrets import token_hex
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))


def settings():
    production = os.getenv("APP_ENV", "development").lower() == "production"
    secret = os.getenv("SECRET_KEY")
    if production and (not secret or len(secret) < 32):
        raise RuntimeError("Set a random SECRET_KEY of at least 32 characters in production.")
    database = {
        "host": os.getenv("DB_HOST", "127.0.0.1"),
        "user": os.getenv("DB_USER", "motor_shop_app"),
        "password": os.getenv("DB_PASSWORD", ""),
        "database": os.getenv("DB_NAME", "motor_shop_db"),
        "port": int(os.getenv("DB_PORT", "3306")),
        "autocommit": True,
        "connection_timeout": 8,
        "time_zone": os.getenv("DB_TIME_ZONE", "+08:00"),
    }
    if ca := os.getenv("DB_SSL_CA"):
        database.update(ssl_ca=ca, ssl_verify_cert=True, ssl_verify_identity=True)
    return {
        "SECRET_KEY": secret or token_hex(32),
        "SESSION_COOKIE_SECURE": production,
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
        "PERMANENT_SESSION_LIFETIME": timedelta(hours=10),
        "MAX_CONTENT_LENGTH": 64 * 1024,
        "DATABASE": database,
        "SHOP_NAME": os.getenv("SHOP_NAME", "MotorShop"),
    }
