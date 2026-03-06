"""
Django test settings for SequoIA platform.
"""

import os

from .base import *  # noqa: F401, F403
from .base import REST_FRAMEWORK, SIMPLE_JWT
from .dev import _DEV_JWT_PRIVATE_KEY, _DEV_JWT_PUBLIC_KEY

SECRET_KEY = os.environ.get("SECRET_KEY", "test-secret-key-for-testing")

DEBUG = False

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]

SIMPLE_JWT = {
    **SIMPLE_JWT,
    "SIGNING_KEY": _DEV_JWT_PRIVATE_KEY,
    "VERIFYING_KEY": _DEV_JWT_PUBLIC_KEY,
}

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_THROTTLE_CLASSES": [],
    "DEFAULT_THROTTLE_RATES": {
        "anon": None,
        "user": None,
        "login": None,
        "api_key": None,
        "export": None,
    },
}

CORS_ALLOW_ALL_ORIGINS = True

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    },
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
}
