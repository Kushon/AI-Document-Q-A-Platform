import asyncio
import json
import logging

from aiokafka import AIOKafkaConsumer

from app.core.config import settings
from app.core.kafka import stop_producer
from app.processing.pipeline import process_document

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def consume() -> None:
    consumer = AIOKafkaConsumer(
        settings.kafka_topic_document_uploaded,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=settings.kafka_consumer_group,
        value_deserializer=lambda v: json.loads(v.decode()),
        auto_offset_reset="earliest",
    )
    await consumer.start()
    logger.info("Kafka consumer запущен, ожидаю события document.uploaded...")

    try:
        async for msg in consumer:
            event = msg.value
            doc_id = event.get("doc_id")
            file_path = event.get("file_path")

            if not doc_id or not file_path:
                logger.warning(f"Некорректное событие: {event}")
                continue

            await process_document(doc_id, file_path)
    finally:
        await consumer.stop()
        await stop_producer()


if __name__ == "__main__":
    asyncio.run(consume())
