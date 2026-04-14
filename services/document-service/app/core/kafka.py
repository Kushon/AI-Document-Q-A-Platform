import json

from aiokafka import AIOKafkaProducer

from app.core.config import settings

_producer: AIOKafkaProducer | None = None


async def get_producer() -> AIOKafkaProducer:
    global _producer
    if _producer is None:
        _producer = AIOKafkaProducer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode(),
        )
        await _producer.start()
    return _producer


async def stop_producer() -> None:
    global _producer
    if _producer:
        await _producer.stop()
        _producer = None


async def publish_document_uploaded(doc_id: str, user_id: str, file_path: str) -> None:
    producer = await get_producer()
    await producer.send(
        settings.kafka_topic_document_uploaded,
        value={"doc_id": doc_id, "user_id": user_id, "file_path": file_path},
    )
