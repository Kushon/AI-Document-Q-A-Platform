from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # PostgreSQL — для обновления статуса документа
    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # MinIO
    minio_host: str = "localhost"
    minio_port: int = 9000
    minio_root_user: str
    minio_root_password: str
    minio_bucket: str = "documents"

    # Kafka
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_topic_document_uploaded: str = "document.uploaded"
    kafka_topic_embedding_completed: str = "embedding.completed"
    kafka_consumer_group: str = "embedding-service"

    # Ollama (OpenAI-compatible)
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_embedding_model: str = "nomic-embed-text"

    # Qdrant
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "documents"

    # Chunking
    chunk_size: int = 500      # токенов / символов
    chunk_overlap: int = 50

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    model_config = {"extra": "ignore"}


settings = Settings()
