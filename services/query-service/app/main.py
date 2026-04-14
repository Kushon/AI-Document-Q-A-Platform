from fastapi import FastAPI

from app.api.query import router as query_router

app = FastAPI(title="Query Service")
app.include_router(query_router)
