"""
Cache Service for Performance Optimization

Implements in-memory caching for:
- RAG query results
- Credit score calculations
- Model predictions
"""

import logging
import hashlib
import json
from typing import Any, Optional, Dict
from datetime import datetime, timedelta
from functools import wraps

logger = logging.getLogger(__name__)


class CacheService:
    """In-memory cache with TTL support"""

    def __init__(self, default_ttl: int = 3600):
        """
        Initialize cache service.

        Args:
            default_ttl: Default time-to-live in seconds (default: 1 hour)
        """
        self._cache: Dict[str, tuple[Any, datetime]] = {}
        self.default_ttl = default_ttl
        self.hit_count = 0
        self.miss_count = 0

    def _generate_key(self, prefix: str, *args, **kwargs) -> str:
        """Generate cache key from arguments"""
        key_data = {
            "prefix": prefix,
            "args": args,
            "kwargs": {k: v for k, v in sorted(kwargs.items())}
        }
        key_str = json.dumps(key_data, sort_keys=True, default=str)
        return hashlib.md5(key_str.encode()).hexdigest()

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired"""
        if key in self._cache:
            value, expiry = self._cache[key]
            if datetime.now() < expiry:
                self.hit_count += 1
                logger.debug(f"Cache hit: {key}")
                return value
            else:
                # Expired - remove from cache
                del self._cache[key]
                logger.debug(f"Cache expired: {key}")

        self.miss_count += 1
        logger.debug(f"Cache miss: {key}")
        return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """Set value in cache with TTL"""
        ttl = ttl or self.default_ttl
        expiry = datetime.now() + timedelta(seconds=ttl)
        self._cache[key] = (value, expiry)
        logger.debug(f"Cache set: {key} (TTL: {ttl}s)")

    def delete(self, key: str):
        """Delete key from cache"""
        if key in self._cache:
            del self._cache[key]
            logger.debug(f"Cache deleted: {key}")

    def clear(self):
        """Clear all cache entries"""
        count = len(self._cache)
        self._cache.clear()
        self.hit_count = 0
        self.miss_count = 0
        logger.info(f"Cache cleared: {count} entries removed")

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total_requests = self.hit_count + self.miss_count
        hit_rate = (self.hit_count / total_requests * 100) if total_requests > 0 else 0

        return {
            "entries": len(self._cache),
            "hits": self.hit_count,
            "misses": self.miss_count,
            "hit_rate": round(hit_rate, 2),
            "total_requests": total_requests
        }

    def cleanup_expired(self):
        """Remove expired entries from cache"""
        now = datetime.now()
        expired_keys = [
            key for key, (_, expiry) in self._cache.items()
            if now >= expiry
        ]

        for key in expired_keys:
            del self._cache[key]

        if expired_keys:
            logger.info(f"Cleaned up {len(expired_keys)} expired cache entries")


# Global cache instance
cache_service = CacheService(default_ttl=1800)  # 30 minutes default


def cached(prefix: str, ttl: Optional[int] = None):
    """
    Decorator for caching function results.

    Args:
        prefix: Cache key prefix
        ttl: Time-to-live in seconds (None = use default)

    Example:
        @cached("credit_score", ttl=3600)
        async def calculate_score(revenue, loan_amount):
            # Expensive calculation
            return score
    """
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Generate cache key
            cache_key = cache_service._generate_key(prefix, *args, **kwargs)

            # Try to get from cache
            cached_result = cache_service.get(cache_key)
            if cached_result is not None:
                return cached_result

            # Execute function
            result = await func(*args, **kwargs)

            # Store in cache
            cache_service.set(cache_key, result, ttl)

            return result

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Generate cache key
            cache_key = cache_service._generate_key(prefix, *args, **kwargs)

            # Try to get from cache
            cached_result = cache_service.get(cache_key)
            if cached_result is not None:
                return cached_result

            # Execute function
            result = func(*args, **kwargs)

            # Store in cache
            cache_service.set(cache_key, result, ttl)

            return result

        # Return appropriate wrapper based on function type
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator
