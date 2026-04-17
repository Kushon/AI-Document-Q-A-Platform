# AI Document Q&A Platform

AI-Document Q&A — инструмент для поиска по документам. Сотрудники загружают PDF и текстовые файлы и задают вопросы на обычном языке — система находит нужные фрагменты и формулирует ответ. Не нужно вручную листать документы: достаточно спросить.

---

## Архитектура

Система построена как набор независимо развёртываемых микросервисов, взаимодействующих через REST (синхронно) и Apache Kafka (асинхронно).

```
Пользователь
 │
 ├── :3000 ──▶ nginx ──▶ frontend-service   (Streamlit UI)
 └── :80   ──▶ nginx ──▶ user-service       POST /auth/*
                    ├──▶ document-service   POST /documents/*
                    └──▶ query-service      POST /query/*

Асинхронный пайплайн:
  document-service ──[document.uploaded]──▶ Kafka ──▶ embedding-service
  embedding-service ──[embedding.completed]──▶ Kafka
```

### Сервисы

| Сервис | Роль | Порт |
|--------|------|------|
| `user-service` | Регистрация, вход, JWT-аутентификация | 8001 |
| `document-service` | Загрузка файлов, метаданные, Kafka producer | 8002 |
| `embedding-service` | Kafka consumer, чанкование, эмбеддинги, Qdrant | — |
| `query-service` | RAG-пайплайн, кэш, вызов LLM | 8004 |
| `frontend-service` | Веб-интерфейс на Streamlit | 3000 |

### Инфраструктура

| Компонент | Технология | Порт |
|-----------|-----------|------|
| Реляционная БД | PostgreSQL 15 | 5432 |
| Объектное хранилище | MinIO | 9000 / 9001 |
| Векторная БД | Qdrant | 6333 |
| Кэш | Valkey 7 | 6379 |
| Брокер сообщений | Apache Kafka 3.7 (KRaft) | 9092 |
| Kafka UI | provectuslabs/kafka-ui | 8080 |
| API Gateway | nginx | 80 / 3000 |

### Модели (через Ollama)

| Модель | Назначение |
|--------|-----------|
| `nomic-embed-text` | Генерация эмбеддингов |
| `gemma3:4b` | Генерация ответов |

---

## Требования

- Docker + Docker Compose
- [Ollama](https://ollama.com), запущенный локально, с предзагруженными моделями:
  ```bash
  ollama pull nomic-embed-text
  ollama pull gemma3:4b
  ```

---

## Быстрый старт

```bash
# 1. Клонировать репозиторий
git clone <repo-url>
cd 2_sem

# 2. Создать .env файл
cp infra/.env.example infra/.env   # заполнить своими значениями

# 3. Запустить всё
docker compose -f infra/docker-compose.yml up -d --build

# 4. Открыть интерфейс
open http://localhost:3000
```

Все сервисы запускаются с проверками готовности (healthcheck). Полный стек готов примерно за 30 секунд.

---

## Переменные окружения

Все секреты хранятся в `infra/.env`. Обязательные переменные:

```env
POSTGRES_USER=rag
POSTGRES_PASSWORD=ragpass
POSTGRES_DB=ragdb

MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin

JWT_SECRET=your-secret-key
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=1440

OLLAMA_CHAT_MODEL=gemma3:4b
OLLAMA_EMBED_MODEL=nomic-embed-text
```

---

## Использование

### Веб-интерфейс (Streamlit)

Открыть **http://localhost:3000**:

1. Зарегистрировать аккаунт или войти.
2. Загрузить PDF или TXT файл (до 50 МБ) через боковую панель.
3. Дождаться статуса документа **ready** (кнопка «Обновить документы»).
4. Раскрыть карточку документа, ввести вопрос и нажать **Ask**.
5. Ответ возвращается с временем отклика, количеством чанков и источником (кэш или LLM).

### REST API

API доступен по адресу **http://localhost:80**. Интерактивная документация каждого сервиса:

| Сервис | Swagger UI |
|--------|-----------|
| user-service | http://localhost:8001/docs |
| document-service | http://localhost:8002/docs |
| query-service | http://localhost:8004/docs |

#### Пример сценария

```bash
# Регистрация
curl -X POST http://localhost/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "secret123"}'

# Вход → получить токен
TOKEN=$(curl -s -X POST http://localhost/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "secret123"}' \
  | jq -r '.access_token')

# Загрузить документ
DOC_ID=$(curl -s -X POST http://localhost/documents/ \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/path/to/document.pdf" \
  | jq -r '.id')

# Опросить статус
curl http://localhost/documents/$DOC_ID \
  -H "Authorization: Bearer $TOKEN"

# Задать вопрос
curl -X POST http://localhost/query/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"doc_id\": \"$DOC_ID\", \"question\": \"О чём этот документ?\"}"
```

---

## End-to-end тесты

```bash
# Требует: pip install requests
python test_e2e.py
```

Скрипт проверяет: аутентификацию, загрузку документа, пайплайн эмбеддингов, Q&A (cache miss/hit), rate limiting (429), удаление документа и персистентность Kafka.

---

## Структура проекта

```
.
├── services/
│   ├── user-service/       # FastAPI — аутентификация, JWT, сессии в Valkey
│   ├── document-service/   # FastAPI — загрузка файлов, MinIO, Kafka producer
│   ├── embedding-service/  # Kafka consumer — чанкование, Qdrant, Ollama
│   ├── query-service/      # FastAPI — RAG-пайплайн, кэш Valkey
│   └── frontend/           # Streamlit UI
├── infra/
│   ├── docker-compose.yml
│   └── .env
├── gateway/
│   └── nginx.conf          # API Gateway + rate limiter + Streamlit proxy
└── test_e2e.py
```

Каждый сервис имеет собственные `pyproject.toml`, `uv.lock` и `Dockerfile`, использующий [uv](https://github.com/astral-sh/uv) как менеджер зависимостей.

---

## Ключевые архитектурные решения

**Почему Kafka, а не RabbitMQ/NATS?**
Переиндексирование требует воспроизведения событий `document.uploaded` (например, при смене модели эмбеддингов). RabbitMQ удаляет сообщения после подтверждения; Kafka хранит их на диске с настраиваемым retention, что позволяет полный replay без повторной загрузки файлов.

**Почему асинхронное индексирование?**
Чанкование и создание эмбеддингов для 50 МБ документа может занять 30–60 секунд. Блокировать HTTP-соединение на это время неприемлемо. `document-service` сразу возвращает `202 Accepted`; `embedding-service` подхватывает работу через Kafka.

**Почему отдельная векторная БД вместо pgvector?**
Qdrant создан специально для приближённого поиска ближайших соседей (HNSW-индекс) с фильтрацией по payload. Фильтрованный векторный поиск по `doc_id` — основной паттерн запросов в системе.

**Почему Valkey?**
Valkey — FOSS-форк Redis, совместимый на уровне API. Python-клиент — пакет `redis` (PyPI), который работает с Valkey по тому же протоколу.

---

## Rate Limiting

Эндпоинт `/query/` ограничен до **10 запросов в минуту на IP** с burst 5, реализовано через nginx. Запросы сверх лимита получают `429 Too Many Requests`.

