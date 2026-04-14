from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.documents import router as documents_router
from app.core.kafka import stop_producer
from app.core.storage import ensure_bucket
from app.db.database import Base, engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    ensure_bucket()
    yield
    await stop_producer()


app = FastAPI(title="Document Service", lifespan=lifespan)
app.include_router(documents_router)
