from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.cache import get_cached, set_cached
from app.core.llm import generate_answer
from app.core.retriever import retrieve
from app.core.security import get_current_user_id

router = APIRouter(prefix="/query", tags=["query"])


class QueryRequest(BaseModel):
    doc_id: str
    question: str


class QueryResponse(BaseModel):
    answer: str
    cached: bool
    chunks_used: int


@router.post("/", response_model=QueryResponse)
async def query(
    body: QueryRequest,
    user_id: str = Depends(get_current_user_id),
):
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="Вопрос не может быть пустым")

    # Проверяем кэш
    cached_answer = await get_cached(body.doc_id, body.question)
    if cached_answer:
        return QueryResponse(answer=cached_answer, cached=True, chunks_used=0)

    # Векторный поиск
    chunks = await retrieve(body.doc_id, body.question)
    if not chunks:
        raise HTTPException(
            status_code=404,
            detail="Документ не найден или ещё не обработан. Проверьте статус документа.",
        )

    # Генерация ответа
    answer = await generate_answer(body.question, chunks)

    # Кэшируем
    await set_cached(body.doc_id, body.question, answer)

    return QueryResponse(answer=answer, cached=False, chunks_used=len(chunks))
