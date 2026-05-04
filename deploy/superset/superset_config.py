"""AQP Superset configuration for the local visualization profile."""
from __future__ import annotations

import os
from urllib.parse import urlparse

from cachelib.redis import RedisCache


SECRET_KEY = os.getenv("SUPERSET_SECRET_KEY", "aqp_superset_dev_secret_change_me")
SQLALCHEMY_DATABASE_URI = os.getenv(
    "SUPERSET__SQLALCHEMY_DATABASE_URI",
    "sqlite:////app/superset_home/superset.db",
)

ENABLE_PROXY_FIX = True
TALISMAN_ENABLED = False
WTF_CSRF_ENABLED = True

FEATURE_FLAGS = {
    "DASHBOARD_RBAC": True,
    "EMBEDDED_SUPERSET": True,
}

GUEST_ROLE_NAME = os.getenv("SUPERSET_GUEST_ROLE_NAME", "Gamma")
GUEST_TOKEN_JWT_SECRET = os.getenv(
    "SUPERSET_GUEST_TOKEN_JWT_SECRET",
    "aqp_superset_guest_secret_change_me",
)
GUEST_TOKEN_JWT_ALGO = "HS256"
GUEST_TOKEN_JWT_EXP_SECONDS = int(os.getenv("SUPERSET_GUEST_TOKEN_JWT_EXP_SECONDS", "300"))

_redis_url = os.getenv("SUPERSET_REDIS_URL", "redis://redis:6379/4")
_results_redis_url = os.getenv("SUPERSET_RESULTS_REDIS_URL", "redis://redis:6379/5")


def _redis_cache_from_url(url: str, *, key_prefix: str, default_db: int) -> RedisCache:
    parsed = urlparse(url)
    return RedisCache(
        host=parsed.hostname or "redis",
        port=parsed.port or 6379,
        password=parsed.password,
        db=int((parsed.path or f"/{default_db}").lstrip("/") or default_db),
        key_prefix=key_prefix,
    )

CACHE_CONFIG = {
    "CACHE_TYPE": "RedisCache",
    "CACHE_REDIS_URL": _redis_url,
    "CACHE_KEY_PREFIX": "aqp_superset_meta_",
    "CACHE_DEFAULT_TIMEOUT": 300,
}

DATA_CACHE_CONFIG = {
    "CACHE_TYPE": "RedisCache",
    "CACHE_REDIS_URL": _redis_url,
    "CACHE_KEY_PREFIX": "aqp_superset_data_",
    "CACHE_DEFAULT_TIMEOUT": int(os.getenv("SUPERSET_DATA_CACHE_TTL_SECONDS", "3600")),
}

FILTER_STATE_CACHE_CONFIG = {
    "CACHE_TYPE": "RedisCache",
    "CACHE_REDIS_URL": _redis_url,
    "CACHE_KEY_PREFIX": "aqp_superset_filter_",
    "CACHE_DEFAULT_TIMEOUT": 60 * 60 * 24 * 90,
}

EXPLORE_FORM_DATA_CACHE_CONFIG = {
    "CACHE_TYPE": "RedisCache",
    "CACHE_REDIS_URL": _redis_url,
    "CACHE_KEY_PREFIX": "aqp_superset_explore_",
    "CACHE_DEFAULT_TIMEOUT": 60 * 60 * 24 * 7,
}

RESULTS_BACKEND = _redis_cache_from_url(
    _results_redis_url,
    key_prefix="aqp_superset_results_",
    default_db=5,
)
RESULTS_BACKEND_USE_MSGPACK = True

SQLLAB_TIMEOUT = int(os.getenv("SUPERSET_SQLLAB_TIMEOUT_SECONDS", "60"))
SQLLAB_ASYNC_TIME_LIMIT_SEC = int(os.getenv("SUPERSET_SQLLAB_ASYNC_TIME_LIMIT_SECONDS", "3600"))

PUBLIC_ROLE_LIKE = None
