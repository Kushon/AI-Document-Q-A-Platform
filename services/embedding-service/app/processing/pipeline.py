import logging

from app.core.db import update_document_status
from app.core.embedder import embed
from app.core.kafka import publish_embedding_completed
from app.core.storage import download_file
from app.core.vector_store import ensure_collection, upsert_chunks
from app.processing.chunker import chunk_text, extract_text

logger = logging.getLogger(__name__)


async def process_document(doc_id: str, file_path: str) -> None:
    """Полный пайплайн: скачать → чанки → эмбеддинги → Qdrant → статус → событие."""
    try:
        await update_document_status(doc_id, "processing")
        logger.info(f"[{doc_id}] Скачиваю файл {file_path}")

        data = download_file(file_path)
        filename = file_path.split("/")[-1]

        text = extract_text(data, filename)
        if not text.strip():
            raise ValueError("Документ пустой или не удалось извлечь текст")

        chunks = chunk_text(text)
        logger.info(f"[{doc_id}] Получено {len(chunks)} чанков")

        vectors = await embed(chunks)

        await ensure_collection(vector_size=len(vectors[0]))
        await upsert_chunks(doc_id, chunks, vectors)
        logger.info(f"[{doc_id}] Сохранено в Qdrant")

        await update_document_status(doc_id, "ready")
        await publish_embedding_completed(doc_id)
        logger.info(f"[{doc_id}] Готово")

    except Exception as e:
        logger.error(f"[{doc_id}] Ошибка: {e}")
        await update_document_status(doc_id, "failed")
