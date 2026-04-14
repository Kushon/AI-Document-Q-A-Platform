import redis.asyncio as aioredis

from app.core.config import settings

redis_client = aioredis.Redis(
    host=settings.redis_host,
    port=settings.redis_port,
    decode_responses=True,
)


async def set_session(user_id: str, token: str) -> None:
    await redis_client.setex(f"session:{user_id}", settings.redis_ttl_seconds, token)


async def get_session(user_id: str) -> str | None:
    return await redis_client.get(f"session:{user_id}")


async def delete_session(user_id: str) -> None:
    await redis_client.delete(f"session:{user_id}")
