from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.auth import router as auth_router
from app.db.database import Base, engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Создать таблицы при старте
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(title="User Service", lifespan=lifespan)
app.include_router(auth_router)
