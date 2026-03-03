"""
Django production settings for SequoIA platform.
"""

import logging as _logging
import os
import sentry_sdk
from django.core.exceptions import ImproperlyConfigured
from .base import *  # noqa: F401, F403

# ---------------------------------------------------------------------------
# Docker Secrets helper
# ---------------------------------------------------------------------------
_secrets_from_env = []


def get_secret(env_key, default=None, required=False):
    """
    Read a secret from Docker Secrets file first, then fall back to env var.
    """
    file_key = f'{env_key}_FILE'
    file_path = os.environ.get(file_key)
    if file_path:
        try:
            with open(file_path, 'r') as f:
                return f.read().strip()
        except (IOError, OSError) as e:
            raise ImproperlyConfigured(
                f"Could not read secret from {file_key}={file_path}: {e}"
            )
    value = os.environ.get(env_key, default)
    if required and not value:
        raise ImproperlyConfigured(
            f"Required setting {env_key} is not set. "
            f"Set it as an environment variable or provide {file_key} for Docker Secrets."
        )
    if value and value != default:
        _secrets_from_env.append(env_key)
    return value


# ---------------------------------------------------------------------------
# Core Django
# ---------------------------------------------------------------------------
SECRET_KEY = get_secret('DJANGO_SECRET_KEY', required=True)
DEBUG = False

# ---------------------------------------------------------------------------
# JWT RS256 keys
# ---------------------------------------------------------------------------
_jwt_signing_key = get_secret('JWT_SIGNING_KEY', required=True)
_jwt_verifying_key = get_secret('JWT_VERIFYING_KEY', required=True)

if '\\n' in _jwt_signing_key:
    _jwt_signing_key = _jwt_signing_key.replace('\\n', '\n')
if '\\n' in _jwt_verifying_key:
    _jwt_verifying_key = _jwt_verifying_key.replace('\\n', '\n')

SIMPLE_JWT = {
    **SIMPLE_JWT,
    'SIGNING_KEY': _jwt_signing_key,
    'VERIFYING_KEY': _jwt_verifying_key,
}

ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get('DJANGO_ALLOWED_HOSTS', '').split(',')
    if h.strip()
]

# ---------------------------------------------------------------------------
# Database — PostgreSQL for production
# ---------------------------------------------------------------------------
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('POSTGRES_DB', 'sequoia'),
        'USER': os.environ.get('POSTGRES_USER', 'sequoia'),
        'PASSWORD': get_secret('POSTGRES_PASSWORD', default=''),
        'HOST': os.environ.get('POSTGRES_HOST', 'localhost'),
        'PORT': os.environ.get('POSTGRES_PORT', '5432'),
        'CONN_MAX_AGE': 600,
    }
}

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get('CORS_ALLOWED_ORIGINS', '').split(',')
    if o.strip()
]
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = CORS_ALLOWED_ORIGINS.copy()

# ---------------------------------------------------------------------------
# Security headers — SSL can be disabled with SECURE_SSL_REDIRECT=false for
# deployments without TLS termination (e.g. internal VPS behind VPN).
# ---------------------------------------------------------------------------
_USE_SSL = os.environ.get('SECURE_SSL_REDIRECT', 'true').lower() == 'true'

if not _USE_SSL:
    _logger = _logging.getLogger('sequoia')
    _logger.warning(
        'SECURITY: SECURE_SSL_REDIRECT is disabled. '
        'Ensure your deployment terminates SSL at the load balancer.'
    )

SECURE_SSL_REDIRECT = _USE_SSL
SESSION_COOKIE_SECURE = _USE_SSL
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SECURE = _USE_SSL
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = 'Lax'
REFRESH_TOKEN_COOKIE_SECURE = _USE_SSL
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

# Content Security Policy — API-only backend, so restrictive policy
# Frontend (served by nginx) has its own CSP
SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin'
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'

if _USE_SSL:
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# ---------------------------------------------------------------------------
# Redis cache (inherits _REDIS_AUTH / _REDIS_HOST from base.py)
# ---------------------------------------------------------------------------
_REDIS_PASSWORD_PROD = get_secret('REDIS_PASSWORD', default='')
_REDIS_AUTH_PROD = f":{_REDIS_PASSWORD_PROD}@" if _REDIS_PASSWORD_PROD else ""
_REDIS_HOST_PROD = os.environ.get('REDIS_HOST', 'localhost')

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            'hosts': [f"redis://{_REDIS_AUTH_PROD}{_REDIS_HOST_PROD}:6379/0"],
        },
    },
}

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': f"redis://{_REDIS_AUTH_PROD}{_REDIS_HOST_PROD}:6379/1",
    }
}

# ---------------------------------------------------------------------------
# Sentry
# ---------------------------------------------------------------------------
sentry_dsn = os.environ.get('SENTRY_DSN')
if sentry_dsn:
    sentry_sdk.init(
        dsn=sentry_dsn,
        traces_sample_rate=0.1,
        send_default_pii=False,
        environment=os.environ.get('ENVIRONMENT', 'production'),
        release=os.environ.get('VERSION', 'unknown'),
    )

# ---------------------------------------------------------------------------
# Logging — structured JSON for production log aggregation
# ---------------------------------------------------------------------------
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'json': {
            '()': 'pythonjsonlogger.json.JsonFormatter',
            'format': '%(asctime)s %(name)s %(levelname)s %(message)s',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'json',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'sequoia': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# ---------------------------------------------------------------------------
# Startup validation
# ---------------------------------------------------------------------------

_required_settings = {
    'ALLOWED_HOSTS': ALLOWED_HOSTS,
    'CORS_ALLOWED_ORIGINS': CORS_ALLOWED_ORIGINS,
}

for _name, _value in _required_settings.items():
    if not _value:
        raise ImproperlyConfigured(
            f"Production setting {_name} is empty. "
            f"Check your environment variables."
        )

if '*' in ALLOWED_HOSTS:
    raise ImproperlyConfigured(
        "ALLOWED_HOSTS contains '*', which is not safe for production."
    )

if len(SECRET_KEY) < 50:
    raise ImproperlyConfigured(
        "SECRET_KEY is too short (must be at least 50 characters)."
    )

# ---------------------------------------------------------------------------
# Trusted proxy IPs for X-Forwarded-For parsing
# Set TRUSTED_PROXY_IPS as comma-separated IPs/CIDRs (e.g., "10.0.0.0/8,172.16.0.0/12")
# When empty, X-Forwarded-For headers are IGNORED — REMOTE_ADDR is used directly
# ---------------------------------------------------------------------------
_trusted_proxy_raw = os.environ.get('TRUSTED_PROXY_IPS', '')
TRUSTED_PROXY_IPS = [ip.strip() for ip in _trusted_proxy_raw.split(',') if ip.strip()] or []

if not TRUSTED_PROXY_IPS:
    _logger = _logging.getLogger('sequoia')
    _logger.warning(
        'SECURITY: TRUSTED_PROXY_IPS not configured. '
        'X-Forwarded-For headers will be ignored — REMOTE_ADDR used for all IP resolution.'
    )

# ClickHouse credentials — require password in production
if not CLICKHOUSE_PASSWORD:
    raise ImproperlyConfigured(
        "SECURITY: CLICKHOUSE_PASSWORD is empty in production. "
        "Set it via environment variable or Docker Secrets (CLICKHOUSE_PASSWORD_FILE)."
    )

if _secrets_from_env:
    _logger = _logging.getLogger('sequoia')
    _logger.warning(
        "SECURITY: Secrets loaded from env vars instead of Docker Secrets files: %s",
        ', '.join(_secrets_from_env),
    )
