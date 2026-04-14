from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Qdrant
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "documents"
    qdrant_top_k: int = 5

    # Ollama (OpenAI-compatible)
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_embedding_model: str = "nomic-embed-text"
    ollama_chat_model: str = "gemma3:4b"

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_ttl_seconds: int = 600  # 10 мин

    # JWT
    jwt_secret: str
    jwt_algorithm: str = "HS256"

    model_config = {"extra": "ignore"}


settings = Settings()
