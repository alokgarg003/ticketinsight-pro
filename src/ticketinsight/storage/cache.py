"""
Caching layer for TicketInsight Pro.

Provides a :class:`CacheManager` that wraps Redis with automatic fallback
to an in-memory dictionary cache when Redis is unavailable.  Includes a
decorator for memoising expensive function calls.

Usage
-----
    from ticketinsight.storage.cache import CacheManager

    cache = CacheManager()
    cache.init_app(config)

    # Direct get/set
    cache.set("key", {"data": 123}, ttl=300)
    value = cache.get("key")

    # Decorator
    @cache.cache_result("expensive_query", ttl=600)
    def expensive_query():
        ...
"""

import functools
import json
import threading
import time
from typing import Any, Callable, Dict, Optional, TypeVar, cast

from ticketinsight.utils.logger import get_logger

logger = get_logger(__name__)

_T = TypeVar("_T")


# ===========================================================================
# In-memory fallback cache
# ===========================================================================

class _InMemoryCache:
    """Thread-safe in-memory cache used as a fallback when Redis is
    unavailable.

    Each entry stores a tuple of ``(value, expiry_timestamp)``.  Entries
    are lazily purged on access.
    """

    def __init__(self) -> None:
        self._store: Dict[str, tuple[Any, Optional[float]]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        """Retrieve a value by key.  Returns ``None`` if missing or expired."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expiry = entry
            if expiry is not None and time.time() > expiry:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Store a value.  Returns ``True`` on success."""
        expiry = (time.time() + ttl) if ttl is not None else None
        with self._lock:
            self._store[key] = (value, expiry)
        return True

    def delete(self, key: str) -> bool:
        """Remove a key.  Returns ``True`` if the key existed."""
        with self._lock:
            if key in self._store:
                del self._store[key]
                return True
            return False

    def exists(self, key: str) -> bool:
        """Return ``True`` if the key exists and has not expired."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return False
            value, expiry = entry
            if expiry is not None and time.time() > expiry:
                del self._store[key]
                return False
            return True

    def clear(self) -> None:
        """Remove all keys."""
        with self._lock:
            self._store.clear()

    def keys(self) -> list[str]:
        """Return a list of non-expired keys."""
        now = time.time()
        with self._lock:
            expired_keys = [
                k for k, (_, exp) in self._store.items()
                if exp is not None and now > exp
            ]
            for k in expired_keys:
                del self._store[k]
            return list(self._store.keys())

    def size(self) -> int:
        """Return the number of non-expired entries."""
        return len(self.keys())

    def get_many(self, keys: list[str]) -> Dict[str, Any]:
        """Retrieve multiple keys at once."""
        result: Dict[str, Any] = {}
        for key in keys:
            value = self.get(key)
            if value is not None:
                result[key] = value
        return result

    def set_many(self, mapping: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        """Store multiple keys at once."""
        for key, value in mapping.items():
            self.set(key, value, ttl=ttl)
        return True

    def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching a simple glob-like pattern.

        Only supports ``*`` as a wildcard.  For full fnmatch support,
        use Redis SCAN + MATCH in production.
        """
        import fnmatch

        deleted = 0
        with self._lock:
            keys_to_delete = [
                k for k in self._store.keys()
                if fnmatch.fnmatch(k, pattern)
            ]
            for k in keys_to_delete:
                del self._store[k]
                deleted += 1
        return deleted

    def info(self) -> Dict[str, Any]:
        """Return diagnostic information about the in-memory cache."""
        return {
            "type": "memory",
            "size": self.size(),
            "keys": self.keys(),
        }


# ===========================================================================
# Cache Manager
# ===========================================================================

class CacheManager:
    """High-level caching façade with Redis primary + in-memory fallback.

    Initialises lazily on first use if :meth:`init_app` was called with
    a config dict.  Otherwise falls back to the in-memory cache
    immediately.

    Attributes
    ----------
    _redis : redis.Redis | None
        Active Redis connection, or ``None`` when using the in-memory
        fallback.
    _fallback : _InMemoryCache
        Always available as a fallback store.
    _prefix : str
        Key prefix used to namespace all keys.
    _default_ttl : int
        Default time-to-live in seconds.
    """

    _instance: Optional["CacheManager"] = None

    def __new__(cls) -> "CacheManager":
        """Enforce singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialised = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialised:
            return
        self._redis: Optional[Any] = None
        self._fallback = _InMemoryCache()
        self._prefix: str = "ticketinsight:"
        self._default_ttl: int = 3600
        self._use_redis: bool = False
        self._redis_url: str = ""
        self._redis_socket_timeout: int = 5
        self._redis_connect_timeout: int = 5
        self._initialised = True

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def init_app(self, config: Dict[str, Any]) -> None:
        """Initialise the cache from an application config dict.

        Parameters
        ----------
        config : dict
            Should contain:
            - ``redis.url`` — Redis connection URL
            - ``redis.cache_ttl`` — default TTL in seconds
        """
        redis_url = config.get("redis", {}).get("url", "redis://localhost:6379/0")
        self._default_ttl = int(config.get("redis", {}).get("cache_ttl", 3600))
        self._redis_socket_timeout = int(
            config.get("redis", {}).get("socket_timeout", 5)
        )
        self._redis_connect_timeout = int(
            config.get("redis", {}).get("socket_connect_timeout", 5)
        )
        self._redis_url = redis_url

        self._connect_redis()

    def _connect_redis(self) -> None:
        """Attempt to connect to Redis.  Falls back to in-memory on failure."""
        try:
            import redis as redis_lib

            self._redis = redis_lib.from_url(
                self._redis_url,
                socket_timeout=self._redis_socket_timeout,
                socket_connect_timeout=self._redis_connect_timeout,
                retry_on_timeout=True,
                decode_responses=True,
            )
            # Ping to verify connectivity
            self._redis.ping()
            self._use_redis = True
            logger.info("Cache connected to Redis at %s", self._redis_url)
        except Exception as exc:
            self._use_redis = False
            self._redis = None
            logger.warning(
                "Redis unavailable at %s — using in-memory cache: %s",
                self._redis_url,
                exc,
            )

    @staticmethod
    def _serialise(value: Any) -> str:
        """Serialise a Python object to a JSON string for storage."""
        return json.dumps(value, default=str, ensure_ascii=False)

    @staticmethod
    def _deserialise(value: str) -> Any:
        """Deserialise a JSON string back to a Python object."""
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value

    def _prefixed_key(self, key: str) -> str:
        """Return the cache key with the namespace prefix applied."""
        return f"{self._prefix}{key}"

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def get(self, key: str) -> Optional[Any]:
        """Retrieve a value from the cache.

        Automatically deserialises JSON values.

        Parameters
        ----------
        key : str
            Cache key (without prefix).

        Returns
        -------
        Any | None
            The cached value, or ``None`` if not found.
        """
        full_key = self._prefixed_key(key)

        if self._use_redis and self._redis is not None:
            try:
                raw = self._redis.get(full_key)
                if raw is not None:
                    return self._deserialise(raw)
                return None
            except Exception as exc:
                logger.warning("Redis GET failed for %s: %s — falling back to memory", key, exc)
                return self._fallback.get(full_key)

        return self._fallback.get(full_key)

    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> bool:
        """Store a value in the cache.

        Parameters
        ----------
        key : str
            Cache key (without prefix).
        value : Any
            Value to cache (will be JSON-serialised).
        ttl : int | None
            Time-to-live in seconds.  Uses the default TTL when ``None``.

        Returns
        -------
        bool
            ``True`` if the write succeeded.
        """
        full_key = self._prefixed_key(key)
        effective_ttl = ttl if ttl is not None else self._default_ttl
        serialised = self._serialise(value)

        if self._use_redis and self._redis is not None:
            try:
                self._redis.setex(full_key, effective_ttl, serialised)
                return True
            except Exception as exc:
                logger.warning("Redis SET failed for %s: %s — falling back to memory", key, exc)

        return self._fallback.set(full_key, serialised, ttl=effective_ttl)

    def delete(self, key: str) -> bool:
        """Remove a key from the cache.

        Parameters
        ----------
        key : str
            Cache key (without prefix).

        Returns
        -------
        bool
            ``True`` if the key existed and was removed.
        """
        full_key = self._prefixed_key(key)
        deleted = False

        if self._use_redis and self._redis is not None:
            try:
                self._redis.delete(full_key)
                deleted = True
            except Exception as exc:
                logger.warning("Redis DELETE failed for %s: %s", key, exc)

        # Always also clear the fallback
        self._fallback.delete(full_key)
        return deleted

    def exists(self, key: str) -> bool:
        """Check whether a key exists (and has not expired).

        Parameters
        ----------
        key : str
            Cache key (without prefix).

        Returns
        -------
        bool
        """
        full_key = self._prefixed_key(key)

        if self._use_redis and self._redis is not None:
            try:
                return bool(self._redis.exists(full_key))
            except Exception as exc:
                logger.warning("Redis EXISTS failed for %s: %s", key, exc)
                return self._fallback.exists(full_key)

        return self._fallback.exists(full_key)

    # ------------------------------------------------------------------
    # Batch operations
    # ------------------------------------------------------------------

    def get_many(self, keys: list[str]) -> Dict[str, Any]:
        """Retrieve multiple keys at once.

        Parameters
        ----------
        keys : list[str]
            Cache keys (without prefix).

        Returns
        -------
        dict[str, Any]
            Mapping of keys that were found to their deserialised values.
        """
        result: Dict[str, Any] = {}

        if self._use_redis and self._redis is not None:
            try:
                full_keys = [self._prefixed_key(k) for k in keys]
                raw_values = self._redis.mget(full_keys)
                for full_key, raw in zip(full_keys, raw_values):
                    if raw is not None:
                        short_key = full_key[len(self._prefix):]
                        result[short_key] = self._deserialise(raw)
                return result
            except Exception as exc:
                logger.warning("Redis MGET failed: %s — falling back to memory", exc)

        # Fallback / in-memory
        full_keys = [self._prefixed_key(k) for k in keys]
        for full_key, short_key in zip(full_keys, keys):
            value = self._fallback.get(full_key)
            if value is not None:
                result[short_key] = self._deserialise(value) if isinstance(value, str) else value
        return result

    def set_many(self, mapping: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        """Store multiple keys at once.

        Parameters
        ----------
        mapping : dict[str, Any]
            Key-value pairs to cache.
        ttl : int | None
            Time-to-live in seconds.

        Returns
        -------
        bool
            ``True`` if all writes succeeded.
        """
        effective_ttl = ttl if ttl is not None else self._default_ttl

        if self._use_redis and self._redis is not None:
            try:
                pipe = self._redis.pipeline()
                for key, value in mapping.items():
                    full_key = self._prefixed_key(key)
                    serialised = self._serialise(value)
                    pipe.setex(full_key, effective_ttl, serialised)
                pipe.execute()
                return True
            except Exception as exc:
                logger.warning("Redis MSET failed: %s — falling back to memory", exc)

        for key, value in mapping.items():
            full_key = self._prefixed_key(key)
            serialised = self._serialise(value)
            self._fallback.set(full_key, serialised, ttl=effective_ttl)
        return True

    # ------------------------------------------------------------------
    # Invalidation
    # ------------------------------------------------------------------

    def invalidate_pattern(self, pattern: str) -> int:
        """Delete all keys matching a glob pattern.

        Uses Redis ``SCAN`` when available, otherwise iterates with
        ``KEYS`` (development only).  The in-memory fallback uses
        ``fnmatch``.

        Parameters
        ----------
        pattern : str
            Glob pattern (applied after the prefix).  E.g. ``"stats:*"``
            matches all keys starting with ``ticketinsight:stats:``.

        Returns
        -------
        int
            Number of keys deleted.
        """
        full_pattern = self._prefixed_key(pattern)
        deleted = 0

        if self._use_redis and self._redis is not None:
            try:
                cursor = 0
                while True:
                    cursor, keys = self._redis.scan(
                        cursor=cursor,
                        match=full_pattern,
                        count=1000,
                    )
                    if keys:
                        deleted += self._redis.delete(*keys)
                    if cursor == 0:
                        break
            except Exception as exc:
                logger.warning("Redis SCAN failed for pattern %s: %s", pattern, exc)

        # Always also clear the fallback
        deleted += self._fallback.delete_pattern(full_pattern)
        return deleted

    def clear(self) -> bool:
        """Delete all keys with the configured prefix.

        Returns
        -------
        bool
        """
        deleted = 0

        if self._use_redis and self._redis is not None:
            try:
                cursor = 0
                while True:
                    cursor, keys = self._redis.scan(
                        cursor=cursor,
                        match=f"{self._prefix}*",
                        count=1000,
                    )
                    if keys:
                        deleted += self._redis.delete(*keys)
                    if cursor == 0:
                        break
            except Exception as exc:
                logger.warning("Redis SCAN (clear) failed: %s", exc)

        self._fallback.clear()
        return deleted > 0

    # ------------------------------------------------------------------
    # Decorator
    # ------------------------------------------------------------------

    def cache_result(
        self,
        key_prefix: str,
        ttl: Optional[int] = None,
        key_builder: Optional[Callable[..., str]] = None,
    ) -> Callable[[Callable[..., _T]], Callable[..., _T]]:
        """Decorator that caches function return values.

        Parameters
        ----------
        key_prefix : str
            Prefix for the generated cache key (appended to the global
            prefix).
        ttl : int | None
            Cache TTL in seconds.  Uses the default when ``None``.
        key_builder : callable | None
            Optional function ``(args, kwargs) -> str`` that produces a
            unique suffix for the cache key.  Defaults to a hash of the
            stringified arguments.

        Returns
        -------
        Callable
            Decorated function.

        Examples
        --------
        >>> @cache.cache_result("user_profile", ttl=300)
        ... def get_user_profile(user_id):
        ...     return db.query(...)
        """
        effective_ttl = ttl if ttl is not None else self._default_ttl

        def decorator(func: Callable[..., _T]) -> Callable[..., _T]:
            @functools.wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> _T:
                # Build the cache key
                if key_builder is not None:
                    key_suffix = key_builder(*args, **kwargs)
                else:
                    # Default: hash the positional and keyword arguments
                    raw = json.dumps(
                        {"args": [str(a) for a in args], "kwargs": kwargs},
                        sort_keys=True,
                        default=str,
                    )
                    key_suffix = hashlib.md5(raw.encode("utf-8")).hexdigest()

                cache_key = f"{key_prefix}:{key_suffix}"

                # Check cache
                cached = self.get(cache_key)
                if cached is not None:
                    logger.debug("Cache HIT for %s", cache_key)
                    return cast(_T, cached)

                # Compute and store
                logger.debug("Cache MISS for %s", cache_key)
                result = func(*args, **kwargs)
                self.set(cache_key, result, ttl=effective_ttl)
                return result

            # Add a convenience method to invalidate this function's cache
            wrapper.cache_invalidate = lambda: self.invalidate_pattern(f"{key_prefix}:*")  # type: ignore[attr-defined]
            wrapper.cache_key_prefix = key_prefix  # type: ignore[attr-defined]

            return wrapper

        return decorator

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Return cache diagnostics.

        Returns
        -------
        dict
            Information about cache type, size, and (if Redis) server info.
        """
        stats: Dict[str, Any] = {
            "backend": "redis" if self._use_redis else "memory",
            "prefix": self._prefix,
            "default_ttl": self._default_ttl,
        }

        if self._use_redis and self._redis is not None:
            try:
                info = self._redis.info(section="default")
                stats.update({
                    "redis_version": info.get("redis_version", "unknown"),
                    "connected_clients": info.get("connected_clients", 0),
                    "used_memory_human": info.get("used_memory_human", "unknown"),
                    "used_memory_peak_human": info.get("used_memory_peak_human", "unknown"),
                    "keyspace_hits": info.get("keyspace_hits", 0),
                    "keyspace_misses": info.get("keyspace_misses", 0),
                    "hit_rate": _safe_divide(
                        info.get("keyspace_hits", 0),
                        info.get("keyspace_hits", 0) + info.get("keyspace_misses", 1),
                    ),
                    "db_size": self._redis.dbsize(),
                    "url": self._redis_url,
                })
            except Exception as exc:
                stats["redis_error"] = str(exc)
                stats.update(self._fallback.info())
        else:
            stats.update(self._fallback.info())

        return stats

    def health_check(self) -> Dict[str, Any]:
        """Return a health-check dict suitable for monitoring endpoints.

        Returns
        -------
        dict
            ``{"healthy": bool, "backend": str, "latency_ms": float, ...}``
        """
        start = time.time()
        healthy = False
        backend = "memory"

        if self._use_redis and self._redis is not None:
            try:
                self._redis.ping()
                healthy = True
                backend = "redis"
            except Exception:
                healthy = False
                backend = "redis (degraded — using fallback)"
        else:
            healthy = True

        latency = (time.time() - start) * 1000

        return {
            "healthy": healthy,
            "backend": backend,
            "latency_ms": round(latency, 3),
            "prefix": self._prefix,
        }

    def __repr__(self) -> str:
        backend = "redis" if self._use_redis else "memory"
        return f"<CacheManager backend={backend} prefix={self._prefix!r}>"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_divide(numerator: float, denominator: float) -> float:
    """Safely compute a ratio, returning 0.0 when the denominator is zero."""
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 4)


# hashlib is needed in cache_result
import hashlib  # noqa: E402
