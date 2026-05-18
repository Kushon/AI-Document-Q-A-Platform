# Grafana дашборды

Импортировать в Grafana через **Dashboards → Import → Upload JSON**.

| Файл | Назначение | Datasource |
|---|---|---|
| `microservices-red.json` | Rate / Errors / Duration p50/p95/p99 на каждый эндпоинт всех сервисов | VictoriaMetrics |
| `kafka.json` | Consumer lag по топикам, throughput брокеров, disk usage | VictoriaMetrics |
| `istio.json` | Success rate, p95 latency между сервисами, outlier-ejections | VictoriaMetrics |
| `rate-limit.json` | Количество 429, top IP с превышениями, остаток квоты | VictoriaMetrics |
| `infra.json` | Postgres connections, Valkey memory, Qdrant disk, MinIO usage | VictoriaMetrics |

Метрики поступают через OpenTelemetry Collector:
- `prometheus-fastapi-instrumentator` на каждом FastAPI сервисе → endpoint `/metrics`
- otel-collector скрейпит pod'ы по annotation `prometheus.io/scrape: "true"`
- otel-collector remote-write'ит в VictoriaMetrics

Для prod дашборды должны быть в Git и провизиониться через
`grafana-operator` (Dashboard CR). Для локального dev — ручной импорт.
