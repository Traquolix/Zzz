"""
Django development settings for SequoIA platform.
"""

import os
from pathlib import Path as _Path

from dotenv import load_dotenv

from .base import *  # noqa: F403
from .base import SIMPLE_JWT

# Load .env.dev from backend root if it exists
_env_dev = _Path(__file__).resolve().parent.parent.parent / ".env.dev"
if _env_dev.exists():
    load_dotenv(_env_dev, override=True)

# Re-read ClickHouse settings from env AFTER load_dotenv.
# base.py reads them at import time (before load_dotenv runs), so the
# star-import captures stale values.  Re-evaluate here.
CLICKHOUSE_HOST = os.environ.get("CLICKHOUSE_HOST", "localhost")
CLICKHOUSE_HTTP_PORT = int(os.environ.get("CLICKHOUSE_HTTP_PORT", 8123))
CLICKHOUSE_DATABASE = os.environ.get("CLICKHOUSE_DATABASE", "sequoia")
CLICKHOUSE_USER = os.environ.get("CLICKHOUSE_USER", "sequoia")
CLICKHOUSE_PASSWORD = os.environ.get("CLICKHOUSE_PASSWORD", "")

SECRET_KEY = "django-insecure-sequoia-dev-key-change-in-production"

DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

# Database — PostgreSQL (Docker container started by `make dev-deps`)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "sequoia"),
        "USER": os.environ.get("POSTGRES_USER", "sequoia"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "CHANGE_ME"),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": 600,
        "CONN_HEALTH_CHECKS": True,
    }
}

# CORS — Allow all in development
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True

# Refresh token cookie — no HTTPS in dev
REFRESH_TOKEN_COOKIE_SECURE = False

# Email — Console backend for development
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Disable password validators in development
AUTH_PASSWORD_VALIDATORS = []

# Channels — Redis (Docker container started by `make dev-deps`)
_DEV_REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
_DEV_REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", "CHANGE_ME")
_DEV_REDIS_AUTH = f":{_DEV_REDIS_PASSWORD}@" if _DEV_REDIS_PASSWORD else ""

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [f"redis://{_DEV_REDIS_AUTH}{_DEV_REDIS_HOST}:6379/0"],
            "capacity": 500,
        },
    },
}

# Redis pub/sub for high-frequency realtime broadcasts (detections, SHM)
REDIS_PUBSUB_URL = f"redis://{_DEV_REDIS_AUTH}{_DEV_REDIS_HOST}:6379/0"

# Cache — Redis
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": f"redis://{_DEV_REDIS_AUTH}{_DEV_REDIS_HOST}:6379/1",
    }
}

# ---------------------------------------------------------------------------
# JWT RS256 dev keys — auto-generated if not provided
# Override via JWT_DEV_PRIVATE_KEY / JWT_DEV_PUBLIC_KEY in .env.dev or env
# ---------------------------------------------------------------------------
_DEV_JWT_PRIVATE_KEY = os.environ.get("JWT_DEV_PRIVATE_KEY", "").replace("\\n", "\n")
_DEV_JWT_PUBLIC_KEY = os.environ.get("JWT_DEV_PUBLIC_KEY", "").replace("\\n", "\n")

if not _DEV_JWT_PRIVATE_KEY or not _DEV_JWT_PUBLIC_KEY:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    _key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    _DEV_JWT_PRIVATE_KEY = _key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    _DEV_JWT_PUBLIC_KEY = (
        _key.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )

SIMPLE_JWT = {
    **SIMPLE_JWT,
    "SIGNING_KEY": _DEV_JWT_PRIVATE_KEY,
    "VERIFYING_KEY": _DEV_JWT_PUBLIC_KEY,
}

# Logging — verbose in dev
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "sequoia": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}
