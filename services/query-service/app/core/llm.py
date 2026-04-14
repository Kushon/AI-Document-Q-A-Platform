from openai import AsyncOpenAI

from app.core.config import settings

_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(base_url=settings.ollama_base_url, api_key="ollama")
    return _client


async def generate_answer(question: str, chunks: list[str]) -> str:
    context = "\n\n---\n\n".join(chunks)
    messages = [
        {
            "role": "system",
            "content": (
                "Ты — ассистент, который отвечает на вопросы строго на основе "
                "предоставленного контекста. Если ответа нет в контексте — скажи об этом."
            ),
        },
        {
            "role": "user",
            "content": f"Контекст:\n{context}\n\nВопрос: {question}",
        },
    ]
    response = await get_client().chat.completions.create(
        model=settings.ollama_chat_model,
        messages=messages,
    )
    return response.choices[0].message.content
