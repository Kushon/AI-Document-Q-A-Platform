"""Locust сценарий нагрузочного тестирования платформы PI (Задание 6.1).

Сценарий генерирует поток запросов через API Gateway (Istio IngressGateway
за HAProxy+Keepalived VIP) в микросервисы. document-service публикует
событие document.uploaded в Kafka — таким образом проверяем что нагрузка
порождает Kafka-трафик (тоже Задание 6.1).

Запуск (внутри docker network к k3d):
  docker run --rm --network k3d-pi-platform \\
    -v $(pwd):/mnt -w /mnt -p 8089:8089 \\
    locustio/locust -f locustfile.py \\
    --host=http://172.30.0.100  # VIP HAProxy

Headless вариант для CI / docs/screenshots:
  locust --headless -u 50 -r 1 -t 5m --host=http://172.30.0.100 \\
    --html=docs/screenshots/locust-baseline.html
"""
from __future__ import annotations

import io
import random
import uuid

from locust import HttpUser, between, task


class PiUser(HttpUser):
    """Один пользователь = один зарегистрированный аккаунт + последовательность действий."""

    wait_time = between(1, 3)

    def on_start(self) -> None:
        """Регистрация + login на старте сессии. JWT сохраняется в self.token."""
        email = f"locust-{uuid.uuid4().hex[:8]}@pi.test"
        password = "locust-pass-1234"
        self.client.post("/auth/register", json={"email": email, "password": password},
                         name="POST /auth/register")
        r = self.client.post("/auth/login", json={"email": email, "password": password},
                             name="POST /auth/login")
        self.token = r.json().get("access_token", "")
        self.headers = {"Authorization": f"Bearer {self.token}"}
        self.doc_ids: list[str] = []

    @task(3)
    def list_documents(self) -> None:
        self.client.get("/documents/", headers=self.headers,
                        name="GET /documents/")

    @task(5)
    def ask_question(self) -> None:
        """Самый частый task — генерирует нагрузку на query-service + LLM.
        Используется для проверки Circuit Breaker (Задание 6.2) и Rate Limit (6.3)."""
        if not self.doc_ids:
            return
        doc_id = random.choice(self.doc_ids)
        questions = [
            "О чём этот документ?",
            "Кто автор?",
            "Дай краткое резюме.",
            "Какие ключевые выводы?",
        ]
        self.client.post(
            "/query/",
            headers=self.headers,
            json={"doc_id": doc_id, "question": random.choice(questions)},
            name="POST /query/",
        )

    @task(1)
    def upload_document(self) -> None:
        """Эмулирует загрузку файла → публикация document.uploaded в Kafka."""
        content = b"Lorem ipsum dolor sit amet. " * 50
        files = {"file": (f"doc-{uuid.uuid4().hex[:6]}.txt", io.BytesIO(content), "text/plain")}
        r = self.client.post("/documents/", headers=self.headers, files=files,
                             name="POST /documents/")
        try:
            doc_id = r.json().get("id")
            if doc_id:
                self.doc_ids.append(doc_id)
        except Exception:
            pass
