# src/utils/cache.py
# Author: Suresh D R | AI Product Developer & Technology Mentor
#
# Thin wrapper around Redis. If Redis is unreachable or disabled, every
# function degrades to a no-op so the rest of the app keeps working --
# caching is a performance optimisation, never a hard dependency.

import json
import logging

import redis

from src.utils.config import settings

logger = logging.getLogger("support_agent.cache")

_client = None


def get_redis():
    global _client
    if not settings.CACHE_ENABLED:
        return None
    if _client is None:
        try:
            _client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                decode_responses=True,
                socket_connect_timeout=2,
            )
            _client.ping()
        except Exception as e:
            logger.warning(f"Redis unavailable, caching disabled: {e}")
            _client = False  # sentinel: tried and failed, don't retry every call
    return _client or None


def cache_get(key: str):
    r = get_redis()
    if not r:
        return None
    try:
        raw = r.get(key)
        return json.loads(raw) if raw else None
    except Exception:
        return None


def cache_set(key: str, value, ttl: int = 300):
    r = get_redis()
    if not r:
        return
    try:
        r.setex(key, ttl, json.dumps(value))
    except Exception:
        pass


def cache_delete(key: str):
    r = get_redis()
    if not r:
        return
    try:
        r.delete(key)
    except Exception:
        pass
