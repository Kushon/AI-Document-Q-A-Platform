import asyncpg

from app.core.config import settings

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            user=settings.postgres_user,
            password=settings.postgres_password,
            database=settings.postgres_db,
            host=settings.postgres_host,
            port=settings.postgres_port,
        )
    return _pool


async def update_document_status(doc_id: str, status: str) -> None:
    pool = await get_pool()
    await pool.execute(
        "UPDATE documents SET status = $1 WHERE id = $2",
        status,
        doc_id,
    )
