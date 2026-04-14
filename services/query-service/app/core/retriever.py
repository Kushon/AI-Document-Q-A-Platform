from openai import AsyncOpenAI
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

from app.core.config import settings

_openai: AsyncOpenAI | None = None
_qdrant: AsyncQdrantClient | None = None


def get_openai() -> AsyncOpenAI:
    global _openai
    if _openai is None:
        _openai = AsyncOpenAI(base_url=settings.ollama_base_url, api_key="ollama")
    return _openai


def get_qdrant() -> AsyncQdrantClient:
    global _qdrant
    if _qdrant is None:
        _qdrant = AsyncQdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
    return _qdrant


async def retrieve(doc_id: str, question: str) -> list[str]:
    """Возвращает топ-k текстовых чанков, релевантных вопросу."""
    emb_response = await get_openai().embeddings.create(
        model=settings.ollama_embedding_model,
        input=[question],
    )
    query_vector = emb_response.data[0].embedding

    results = await get_qdrant().query_points(
        collection_name=settings.qdrant_collection,
        query=query_vector,
        query_filter=Filter(
            must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
        ),
        limit=settings.qdrant_top_k,
    )
    return [hit.payload["text"] for hit in results.points]
