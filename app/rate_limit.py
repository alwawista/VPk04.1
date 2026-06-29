from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from dataclasses import dataclass

try:
    import redis.asyncio as redis_async
except Exception:  # pragma: no cover - redis import depends on installed extras
    redis_async = None


class RateLimitExceeded(Exception):
    def __init__(self, key: str, limit: int, retry_after: int) -> None:
        self.key = key
        self.limit = limit
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded for {key}")


@dataclass(frozen=True)
class RateLimitRule:
    key: str
    limit: int
    window_seconds: int = 60


class InMemoryWindowLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def check(self, rule: RateLimitRule) -> None:
        if rule.limit <= 0:
            return
        now = time.monotonic()
        cutoff = now - rule.window_seconds
        async with self._lock:
            bucket = self._events[rule.key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= rule.limit:
                retry_after = max(1, int(rule.window_seconds - (now - bucket[0])))
                raise RateLimitExceeded(rule.key, rule.limit, retry_after)
            bucket.append(now)


class RedisFixedWindowLimiter:
    def __init__(self, redis_url: str) -> None:
        if redis_async is None:
            raise RuntimeError("redis package is not available")
        self._redis = redis_async.from_url(redis_url, encoding="utf-8", decode_responses=True)

    async def check(self, rule: RateLimitRule) -> None:
        if rule.limit <= 0:
            return
        now_window = int(time.time() // rule.window_seconds)
        redis_key = f"{rule.key}:{now_window}"
        count = await self._redis.incr(redis_key)
        if count == 1:
            await self._redis.expire(redis_key, rule.window_seconds + 1)
        if count > rule.limit:
            ttl = await self._redis.ttl(redis_key)
            raise RateLimitExceeded(rule.key, rule.limit, max(1, int(ttl)))

    async def close(self) -> None:
        await self._redis.aclose()


class RateLimiter:
    def __init__(self, redis_url: str | None = None) -> None:
        self.mode = "memory"
        self.warning = "In-memory limiter is demo-only and resets on restart."
        self._backend: InMemoryWindowLimiter | RedisFixedWindowLimiter = InMemoryWindowLimiter()
        if redis_url:
            try:
                self._backend = RedisFixedWindowLimiter(redis_url)
                self.mode = "redis"
                self.warning = ""
            except Exception:
                self._backend = InMemoryWindowLimiter()

    async def check_many(self, rules: list[RateLimitRule]) -> None:
        for rule in rules:
            await self._backend.check(rule)

    async def close(self) -> None:
        close = getattr(self._backend, "close", None)
        if close:
            await close()
