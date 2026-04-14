import hashlib

import redis.asyncio as aioredis

from app.core.config import settings

_client: aioredis.Redis | None = None


def get_client() -> aioredis.Redis:
    global _client
    if _client is None:
        _client = aioredis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            decode_responses=True,
        )
    return _client


def _cache_key(doc_id: str, question: str) -> str:
    h = hashlib.sha256(f"{doc_id}:{question}".encode()).hexdigest()
    return f"query:{h}"


async def get_cached(doc_id: str, question: str) -> str | None:
    return await get_client().get(_cache_key(doc_id, question))


async def set_cached(doc_id: str, question: str, answer: str) -> None:
    await get_client().setex(_cache_key(doc_id, question), settings.redis_ttl_seconds, answer)
