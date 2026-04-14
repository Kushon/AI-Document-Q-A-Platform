from openai import AsyncOpenAI

from app.core.config import settings

_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            base_url=settings.ollama_base_url,
            api_key="ollama",  # Ollama не требует ключ, но поле обязательно
        )
    return _client


async def embed(texts: list[str]) -> list[list[float]]:
    """Возвращает список векторов для списка текстов."""
    client = get_client()
    response = await client.embeddings.create(
        model=settings.ollama_embedding_model,
        input=texts,
    )
    return [item.embedding for item in response.data]
