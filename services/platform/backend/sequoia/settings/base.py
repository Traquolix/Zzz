"""
Django base settings for SequoIA platform.
Shared settings for all environments.
"""

import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Data directory for cable files, infrastructure config, etc.
# In development: repo_root/infrastructure/clickhouse/cables
# In Docker: /infrastructure/clickhouse/cables (mounted volume)
DATA_DIR = Path(
    os.environ.get("SEQUOIA_DATA_DIR", BASE_DIR.parent.parent.parent / "infrastructure")
)

# Kafka and Schema Registry
SCHEMA_REGISTRY_URL = os.environ.get("SCHEMA_REGISTRY_URL", "http://schema-registry:8081")

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "drf_spectacular",
    "channels",
    # Local apps
    "apps.shared",
    "apps.organizations",
    "apps.accounts",
    "apps.fibers",
    "apps.monitoring",
    "apps.alerting",
    "apps.preferences",
    "apps.reporting",
    "apps.realtime",
    "apps.api_keys",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.shared.middleware.RequestLoggingMiddleware",
]

ROOT_URLCONF = "sequoia.urls"

# API endpoints use no trailing slash
APPEND_SLASH = False

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "sequoia.wsgi.application"
ASGI_APPLICATION = "sequoia.asgi.application"

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Europe/Paris"
USE_I18N = True
USE_TZ = True

LANGUAGES = [
    ("en", "English"),
    ("fr", "French"),
]

LOCALE_PATHS = [
    BASE_DIR / "locale",
]

# Static files
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Custom user model
AUTH_USER_MODEL = "accounts.User"

# REST Framework configuration
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "apps.accounts.oidc.AuthentikOIDCAuthentication",
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "apps.api_keys.authentication.APIKeyAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("apps.shared.permissions.IsActiveUser",),
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "5/minute",
        "user": "3000/hour",
        "login": "5/minute",
        "api_key": "100/hour",
        "export": "10/hour",
        "export_estimate": "60/hour",
        "public_api": "300/hour",
    },
    "DATETIME_FORMAT": "%Y-%m-%dT%H:%M:%SZ",
    "DATETIME_INPUT_FORMATS": ["iso-8601"],
    "DATE_FORMAT": "%Y-%m-%d",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.shared.exception_handlers.custom_exception_handler",
}

# OpenAPI/Swagger documentation
SPECTACULAR_SETTINGS = {
    "TITLE": "SequoIA Platform API",
    "DESCRIPTION": (
        "API for the SequoIA DAS traffic monitoring platform.\n\n"
        "## Authentication\n\n"
        "Uses Authentik OIDC (primary) or JWT with RS256 (legacy).\n"
        "Include token in header: `Authorization: Bearer <token>`\n"
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}

# JWT configuration — RS256 asymmetric keys
# SIGNING_KEY and VERIFYING_KEY are set per-environment (dev.py / prod.py).
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "RS256",
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

# Refresh token cookie settings (httpOnly — not accessible to JS)
REFRESH_TOKEN_COOKIE_NAME = "sequoia_refresh"
REFRESH_TOKEN_COOKIE_HTTPONLY = True
REFRESH_TOKEN_COOKIE_SAMESITE = "Lax"
REFRESH_TOKEN_COOKIE_PATH = "/api/auth/"

# Session hint cookie — JS-readable flag so the frontend knows whether to
# attempt a token refresh on startup (avoids a blind POST that always 401s
# when no session exists).
SESSION_HINT_COOKIE_NAME = "has_session"

# Authentik OIDC settings
# All three must be set for OIDC auth to activate. If any is missing, OIDC is skipped.
OIDC_ISSUER_URL = os.environ.get("OIDC_ISSUER_URL", "")
OIDC_AUDIENCE = os.environ.get("OIDC_AUDIENCE", "")  # = Authentik Client ID
OIDC_JWKS_URL = os.environ.get("OIDC_JWKS_URL", "")

_oidc_vars = {
    "OIDC_ISSUER_URL": OIDC_ISSUER_URL,
    "OIDC_AUDIENCE": OIDC_AUDIENCE,
    "OIDC_JWKS_URL": OIDC_JWKS_URL,
}
_oidc_set = {k for k, v in _oidc_vars.items() if v}
if _oidc_set and _oidc_set != set(_oidc_vars):
    import logging as _oidc_logging

    _oidc_logging.getLogger(__name__).warning(
        "OIDC partially configured: %s set, %s missing. OIDC auth will NOT activate.",
        ", ".join(sorted(_oidc_set)),
        ", ".join(sorted(set(_oidc_vars) - _oidc_set)),
    )

# Frontend URL
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:5173")

# ClickHouse connection settings
CLICKHOUSE_HOST = os.environ.get("CLICKHOUSE_HOST", "localhost")
CLICKHOUSE_HTTP_PORT = int(os.environ.get("CLICKHOUSE_HTTP_PORT", 8123))
CLICKHOUSE_DATABASE = os.environ.get("CLICKHOUSE_DATABASE", "sequoia")
CLICKHOUSE_USER = os.environ.get("CLICKHOUSE_USER", "sequoia")
CLICKHOUSE_PASSWORD = os.environ.get("CLICKHOUSE_PASSWORD", "")

# Kafka
KAFKA_BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "")
KAFKA_DETECTIONS_TOPIC = os.environ.get("KAFKA_DETECTIONS_TOPIC", "prod.detections")
KAFKA_CONSUMER_GROUP = os.environ.get("KAFKA_CONSUMER_GROUP", "sequoia-realtime-bridge")

# Realtime data source: 'auto' | 'simulation' | 'kafka'
# auto: tries Kafka if KAFKA_BOOTSTRAP_SERVERS is set, falls back to simulation
REALTIME_SOURCE = os.environ.get("REALTIME_SOURCE", "auto")

# Auto-start simulation on first ASGI scope (first HTTP/WebSocket request).
# Enabled by default so demo deployments have vehicles on first visit.
# Disable per deployment with AUTO_START_SIMULATION=false.
REALTIME_AUTO_START_SIMULATION = os.environ.get("AUTO_START_SIMULATION", "true").lower() == "true"

# Redis / Channels
_REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
_REDIS_PORT = os.environ.get("REDIS_PORT", "6379")
_REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", "")
_REDIS_AUTH = f":{_REDIS_PASSWORD}@" if _REDIS_PASSWORD else ""
_REDIS_CHANNEL_DB = os.environ.get("REDIS_CHANNEL_DB", "0")
_REDIS_CACHE_DB = os.environ.get("REDIS_CACHE_DB", "1")

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [f"redis://{_REDIS_AUTH}{_REDIS_HOST}:{_REDIS_PORT}/{_REDIS_CHANNEL_DB}"],
            # Only incidents + fibers use the channel layer now (low-frequency).
            # 500 buffers burst deliveries without excessive memory. Default is 100.
            "capacity": 500,
        },
    },
}

# Redis pub/sub for high-frequency realtime broadcasts (detections, SHM)
# Uses the same Redis instance and DB as the channel layer
REDIS_PUBSUB_URL = f"redis://{_REDIS_AUTH}{_REDIS_HOST}:{_REDIS_PORT}/{_REDIS_CHANNEL_DB}"

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": f"redis://{_REDIS_AUTH}{_REDIS_HOST}:{_REDIS_PORT}/{_REDIS_CACHE_DB}",
    }
}

# Logging configuration
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_id": {
            "()": "apps.shared.logging_utils.RequestIdFilter",
        },
    },
    "formatters": {
        "verbose": {
            "format": "[{request_id}] {levelname} {asctime} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
            "filters": ["request_id"],
        },
    },
    "loggers": {
        "sequoia": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "sequoia.shared.middleware": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "django": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}

# Email configuration
EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = os.environ.get("EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", 587))
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "True").lower() == "true"
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "noreply@sequoia.local")
