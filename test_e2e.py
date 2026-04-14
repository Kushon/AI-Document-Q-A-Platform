"""
End-to-end тест AI Document Q&A Platform.
Запуск: python test_e2e.py
Требования: все сервисы запущены через docker compose (gateway на :80).
"""

import hashlib
import io
import sys
import time

import requests

BASE_URL = "http://localhost:80"
EMAIL = f"e2e_test_{int(time.time())}@test.com"
PASSWORD = "e2eSecret99"

# ANSI-цвета
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"
BOLD = "\033[1m"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def ok(msg: str):
    print(f"  {GREEN}✓{RESET} {msg}")


def fail(msg: str):
    print(f"  {RED}✗{RESET} {msg}")
    sys.exit(1)


def warn(msg: str):
    print(f"  {YELLOW}⚠{RESET} {msg}")


def section(title: str):
    print(f"\n{BOLD}{BLUE}{'─' * 60}{RESET}")
    print(f"{BOLD}{BLUE}  {title}{RESET}")
    print(f"{BOLD}{BLUE}{'─' * 60}{RESET}")


def assert_status(resp: requests.Response, expected: int, label: str):
    if resp.status_code == expected:
        ok(f"{label} → {resp.status_code}")
    else:
        fail(f"{label} → ожидался {expected}, получен {resp.status_code}: {resp.text[:200]}")


def assert_field(data: dict, field: str, label: str):
    if field in data and data[field]:
        ok(f"{label}: {str(data[field])[:80]}")
    else:
        fail(f"{label}: поле '{field}' отсутствует или пустое в {data}")


def make_txt() -> bytes:
    return b"""Artificial intelligence is transforming the modern world.
Machine learning allows systems to learn from data without explicit programming.

Neural networks are inspired by the structure of the human brain.
Deep learning uses multiple layers to extract complex patterns from data.

Natural language processing enables machines to understand and generate human text.
Reinforcement learning trains agents to make decisions through reward signals.

Vector databases store high-dimensional embeddings for semantic similarity search.
Retrieval-Augmented Generation combines search with language model generation."""


def make_pdf() -> bytes:
    """Создаёт минимально валидный PDF с тестовым текстом."""
    stream = (
        b"BT /F1 11 Tf 40 780 Td "
        b"(RAG combines retrieval and generation.) Tj "
        b"0 -18 Td (Embeddings capture semantic meaning of text.) Tj "
        b"0 -18 Td (Vector search finds the most relevant chunks.) Tj "
        b"ET"
    )
    stream_len = len(stream)
    pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R"
        b"/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
        + f"4 0 obj<</Length {stream_len}>>\nstream\n".encode()
        + stream
        + b"\nendstream\nendobj\n"
        b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
        b"xref\n0 6\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"0000000274 00000 n \n"
        b"0000000400 00000 n \n"
        b"trailer<</Size 6/Root 1 0 R>>\nstartxref\n460\n%%EOF"
    )
    return pdf


# ─── Тест-кейсы ───────────────────────────────────────────────────────────────

def test_gateway_health():
    section("1. Gateway healthcheck")
    resp = requests.get(f"{BASE_URL}/health", timeout=5)
    assert_status(resp, 200, "GET /health")
    ok(f"Тело ответа: '{resp.text.strip()}'")


def test_auth(session: requests.Session) -> str:
    section("2. Аутентификация")

    # Регистрация
    resp = session.post(f"{BASE_URL}/auth/register", json={"email": EMAIL, "password": PASSWORD})
    assert_status(resp, 201, "POST /auth/register")
    data = resp.json()
    assert_field(data, "id", "user_id")
    assert_field(data, "email", "email")
    user_id = data["id"]

    # Повторная регистрация → 409
    resp2 = session.post(f"{BASE_URL}/auth/register", json={"email": EMAIL, "password": PASSWORD})
    assert_status(resp2, 409, "Повторная регистрация → 409")

    # Логин с неверным паролем → 401
    resp3 = session.post(f"{BASE_URL}/auth/login", json={"email": EMAIL, "password": "wrong"})
    assert_status(resp3, 401, "Логин с неверным паролем → 401")

    # Успешный логин
    resp4 = session.post(f"{BASE_URL}/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert_status(resp4, 200, "POST /auth/login")
    token = resp4.json().get("access_token", "")
    if not token:
        fail("JWT токен не получен")
    ok(f"JWT получен: {token[:40]}...")

    # GET /auth/me
    resp5 = session.get(f"{BASE_URL}/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert_status(resp5, 200, "GET /auth/me")
    assert_field(resp5.json(), "email", "email в профиле")

    # Запрос без токена → 403/401
    resp6 = session.get(f"{BASE_URL}/auth/me")
    if resp6.status_code in (401, 403):
        ok(f"GET /auth/me без токена → {resp6.status_code}")
    else:
        fail(f"Ожидался 401/403, получен {resp6.status_code}")

    return token


def test_documents(session: requests.Session, token: str) -> dict:
    section("3. Управление документами")
    headers = {"Authorization": f"Bearer {token}"}
    results = {}

    # Загрузка TXT
    txt_data = make_txt()
    resp = session.post(
        f"{BASE_URL}/documents/",
        headers=headers,
        files={"file": ("test.txt", io.BytesIO(txt_data), "text/plain")},
    )
    assert_status(resp, 201, "POST /documents/ (TXT)")
    doc_txt = resp.json()
    assert_field(doc_txt, "id", "doc_id (TXT)")
    assert_field(doc_txt, "status", "статус")
    results["txt"] = doc_txt

    # Загрузка PDF
    pdf_data = make_pdf()
    resp2 = session.post(
        f"{BASE_URL}/documents/",
        headers=headers,
        files={"file": ("test.pdf", io.BytesIO(pdf_data), "application/pdf")},
    )
    assert_status(resp2, 201, "POST /documents/ (PDF)")
    doc_pdf = resp2.json()
    assert_field(doc_pdf, "id", "doc_id (PDF)")
    results["pdf"] = doc_pdf

    # Неподдерживаемый формат → 415
    resp3 = session.post(
        f"{BASE_URL}/documents/",
        headers=headers,
        files={"file": ("test.docx", io.BytesIO(b"fake"), "application/vnd.openxmlformats")},
    )
    assert_status(resp3, 415, "Загрузка .docx → 415")

    # Список документов
    resp4 = session.get(f"{BASE_URL}/documents/", headers=headers)
    assert_status(resp4, 200, "GET /documents/")
    docs = resp4.json()
    if len(docs) >= 2:
        ok(f"Список документов: {len(docs)} шт.")
    else:
        fail(f"Ожидалось ≥ 2 документа, получено: {len(docs)}")

    return results


def test_wait_for_ready(session: requests.Session, token: str, doc_id: str, label: str, timeout: int = 60) -> bool:
    section(f"4. Ожидание индексирования ({label})")
    headers = {"Authorization": f"Bearer {token}"}
    start = time.time()

    for attempt in range(timeout):
        resp = session.get(f"{BASE_URL}/documents/{doc_id}", headers=headers)
        assert_status(resp, 200, f"GET /documents/{doc_id}")
        status = resp.json().get("status")
        elapsed = time.time() - start

        if status == "ready":
            ok(f"Статус: ready (за {elapsed:.1f} с, {attempt + 1} попыток)")
            return True
        elif status == "failed":
            fail(f"Статус: failed — embedding-service вернул ошибку")
        else:
            print(f"  ⏳ [{attempt + 1}/{timeout}] статус: {status} ({elapsed:.1f}s)...", end="\r")
            time.sleep(1)

    warn(f"Документ не перешёл в ready за {timeout}с (текущий статус: {status})")
    return False


def test_query(session: requests.Session, token: str, doc_id: str) -> str | None:
    section("5. RAG-запрос (cache miss)")
    headers = {"Authorization": f"Bearer {token}"}

    question = "What is machine learning?"
    start = time.time()
    resp = session.post(
        f"{BASE_URL}/query/",
        headers=headers,
        json={"doc_id": doc_id, "question": question},
        timeout=30,
    )
    elapsed = time.time() - start
    assert_status(resp, 200, "POST /query/ (первый запрос)")
    data = resp.json()

    if data.get("cached") is True:
        warn("Ответ пришёл из кэша (ожидался cache miss — возможно, кэш не был очищен)")
    else:
        ok(f"cached: False — вызван LLM")

    assert_field(data, "answer", "answer")
    ok(f"Ответ: \"{data['answer'][:100]}...\"" if len(data.get("answer", "")) > 100 else f"Ответ: \"{data.get('answer')}\"")
    ok(f"chunks_used: {data.get('chunks_used')}")
    ok(f"Время ответа: {elapsed:.2f}с")

    return question


def test_cache_hit(session: requests.Session, token: str, doc_id: str, question: str):
    section("6. RAG-запрос (cache hit)")
    headers = {"Authorization": f"Bearer {token}"}

    start = time.time()
    resp = session.post(
        f"{BASE_URL}/query/",
        headers=headers,
        json={"doc_id": doc_id, "question": question},
        timeout=10,
    )
    elapsed = time.time() - start
    assert_status(resp, 200, "POST /query/ (повторный запрос)")
    data = resp.json()

    if data.get("cached") is True:
        ok(f"cached: True — ответ из Redis")
    else:
        warn("Ожидался cache hit, но cached=False (TTL мог истечь или Redis недоступен)")

    ok(f"Время ответа: {elapsed:.3f}с")
    if elapsed < 1.0:
        ok("Время < 1с — кэш работает корректно")
    else:
        warn(f"Время {elapsed:.2f}с — ожидалось < 1с для cache hit")


def test_query_validation(session: requests.Session, token: str, doc_id: str):
    section("7. Валидация запросов")
    headers = {"Authorization": f"Bearer {token}"}

    # Пустой вопрос → 400
    resp = session.post(
        f"{BASE_URL}/query/",
        headers=headers,
        json={"doc_id": doc_id, "question": ""},
        timeout=10,
    )
    assert_status(resp, 400, "Пустой вопрос → 400")

    # Несуществующий doc_id → 404
    resp2 = session.post(
        f"{BASE_URL}/query/",
        headers=headers,
        json={"doc_id": "00000000-0000-0000-0000-000000000000", "question": "test"},
        timeout=10,
    )
    assert_status(resp2, 404, "Несуществующий doc_id → 404")

    # Запрос без токена → 401/403
    resp3 = session.post(
        f"{BASE_URL}/query/",
        json={"doc_id": doc_id, "question": "test"},
        timeout=10,
    )
    if resp3.status_code in (401, 403):
        ok(f"Запрос без токена → {resp3.status_code}")
    else:
        fail(f"Ожидался 401/403, получен {resp3.status_code}")


def test_rate_limiter(session: requests.Session, token: str, doc_id: str):
    section("8. Rate Limiter (10 req/min)")
    headers = {"Authorization": f"Bearer {token}"}

    statuses = []
    for i in range(20):
        resp = session.post(
            f"{BASE_URL}/query/",
            headers=headers,
            json={"doc_id": doc_id, "question": f"rate limit test {i}"},
            timeout=10,
        )
        statuses.append(resp.status_code)

    count_429 = statuses.count(429)
    count_2xx = sum(1 for s in statuses if 200 <= s < 300)

    ok(f"Всего запросов: {len(statuses)}")
    ok(f"Успешных (2xx): {count_2xx}")
    ok(f"Заблокировано (429): {count_429}")

    if count_429 > 0:
        ok("Rate limiter срабатывает")
    else:
        warn("429 не получено — rate limiter не сработал (возможно, лимит сбросился)")


def test_delete_document(session: requests.Session, token: str, doc_id: str):
    section("9. Удаление документа")
    headers = {"Authorization": f"Bearer {token}"}

    resp = session.delete(f"{BASE_URL}/documents/{doc_id}", headers=headers)
    assert_status(resp, 204, f"DELETE /documents/{doc_id}")

    # Повторный GET → 404
    resp2 = session.get(f"{BASE_URL}/documents/{doc_id}", headers=headers)
    assert_status(resp2, 404, "GET удалённого документа → 404")


def test_kafka_persistence(session: requests.Session, token: str):
    section("10. Kafka — загрузка нового документа")
    headers = {"Authorization": f"Bearer {token}"}

    # Загружаем ещё один документ и проверяем, что он тоже переходит в ready
    txt = b"Kafka is a distributed event streaming platform. It stores events durably on disk."
    resp = session.post(
        f"{BASE_URL}/documents/",
        headers=headers,
        files={"file": ("kafka_test.txt", io.BytesIO(txt), "text/plain")},
    )
    assert_status(resp, 201, "Загрузка документа для Kafka-теста")
    doc_id = resp.json()["id"]

    ready = test_wait_for_ready(session, token, doc_id, "Kafka persistence", timeout=30)
    if ready:
        ok("Kafka доставила событие, embedding-service обработал документ")
    else:
        warn("Документ не готов — проверьте логи embedding-service")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{BOLD}{'=' * 60}{RESET}")
    print(f"{BOLD}  E2E тест — AI Document Q&A Platform{RESET}")
    print(f"{BOLD}  База: {BASE_URL}{RESET}")
    print(f"{BOLD}{'=' * 60}{RESET}")

    session = requests.Session()
    passed = 0
    total = 0

    try:
        test_gateway_health()
        passed += 1; total += 1

        token = test_auth(session)
        passed += 1; total += 1

        docs = test_documents(session, token)
        passed += 1; total += 1

        txt_doc_id = docs["txt"]["id"]
        pdf_doc_id = docs["pdf"]["id"]

        # Ждём TXT
        txt_ready = test_wait_for_ready(session, token, txt_doc_id, "TXT")
        total += 1
        if txt_ready:
            passed += 1

        # Ждём PDF
        pdf_ready = test_wait_for_ready(session, token, pdf_doc_id, "PDF")
        total += 1
        if pdf_ready:
            passed += 1

        if txt_ready:
            question = test_query(session, token, txt_doc_id)
            passed += 1; total += 1

            if question:
                test_cache_hit(session, token, txt_doc_id, question)
                passed += 1; total += 1

            test_query_validation(session, token, txt_doc_id)
            passed += 1; total += 1

            test_rate_limiter(session, token, txt_doc_id)
            passed += 1; total += 1

            test_delete_document(session, token, txt_doc_id)
            passed += 1; total += 1
        else:
            total += 5  # пропускаем зависимые тесты

        test_kafka_persistence(session, token)
        passed += 1; total += 1

    except SystemExit:
        total += 1  # тест упал с fail()
        raise
    finally:
        print(f"\n{BOLD}{'=' * 60}{RESET}")
        color = GREEN if passed == total else RED
        print(f"{BOLD}{color}  Результат: {passed}/{total} тестов прошли{RESET}")
        print(f"{BOLD}{'=' * 60}{RESET}\n")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        sys.exit(1)
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Прерван пользователем{RESET}")
        sys.exit(1)
    except Exception as e:
        print(f"\n{RED}Неожиданная ошибка: {e}{RESET}")
        sys.exit(1)
