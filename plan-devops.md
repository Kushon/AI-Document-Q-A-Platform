# План реализации — DevOps-фаза (Блок 2)

> Перенос существующей платформы AI Document Q&A с docker-compose на полноценный Kubernetes-стек: IaC, GitOps, Service Mesh, Observability, CI/CD, нагрузочные тесты.

## Контекст

Уже готово (Блок 1, [plan.md](./plan.md)):
- 4 микросервиса на FastAPI: `user-service`, `document-service`, `embedding-service`, `query-service` + `frontend` (Streamlit)
- Инфраструктура в docker-compose: Postgres, MinIO, Qdrant, Valkey, Kafka, nginx
- e2e-тесты `test_e2e.py`

Целевое состояние: всё то же самое, но запущенное в k3d-кластере с полным DevOps-обвязкой.

## Согласованные технологические решения

| Область | Выбор | Альтернативы (для сравнения в отчёте) |
|---|---|---|
| K8s distro | **k3d** (k3s в Docker, 2 ноды) | Minikube, Talos |
| CNI | **Cilium** + Hubble (eBPF) | Calico, Flannel |
| Автоскейлинг | **Cluster Autoscaler** | Karpenter (только cloud) |
| IaC | **Terraform** (providers: kubernetes, helm) | Pulumi |
| GitOps | **ArgoCD** + App-of-Apps | Flux |
| Конф-мгмт | **Ansible Role** (Strimzi/Kafka) | Helm |
| Service Mesh | **Istio** (sidecar) | Linkerd |
| Ingress | **Istio IngressGateway** + HAProxy + Keepalived (декларативно) | Nginx Ingress, Traefik |
| Rate Limit | **Envoy Rate Limit Service** + Valkey | NGINX, Kong |
| Метрики | **VictoriaMetrics Cluster** | Prometheus, InfluxDB |
| Логи | **VictoriaLogs** | Loki, Elasticsearch, SigNoz |
| Трейсы | **Tempo** | Jaeger, Uptrace |
| Сборщик | **OpenTelemetry Collector** | — |
| Визуализация | **Grafana** | — |
| Алерты | **Alertmanager** + **vmalert** | — |
| Git remote | **GitHub** (существующий репозиторий) | Gitea |
| CI | **GitHub Actions Self-Hosted Runner** (в k8s) | GitLab Runner, Tekton |
| Build образов | **Kaniko** (без docker-in-docker) | BuildKit |
| Registry | **k3d local registry** | Harbor |
| Нагрузка | **Locust** | k6 |

**Формат сдачи: гибрид** — критическое запускаем реально для скриншотов и e2e-проверок (k3d, Cilium, ArgoCD, Strimzi/Kafka, Istio, Observability, GitHub Actions, Locust, HAProxy+Keepalived внутри Docker-сети, Cluster Autoscaler). Остальное (Karpenter, Talos) — описано декларативно с обоснованием в отчёте.

## Архитектурные решения (после ревью)

### Source of truth — чёткая иерархия

Чтобы избежать конфликта между Terraform/ArgoCD/Ansible:

| Слой | Инструмент | Что создаёт | Когда работает |
|---|---|---|---|
| **Bootstrap** | Terraform | k3d-кластер (через k3d-provider), базовые namespaces, ArgoCD (Helm), root-Application | Один раз при инициализации |
| **Platform + workloads** | ArgoCD | Всё остальное: Istio, Strimzi, observability, микросервисы, network policies | Runtime — следит за Git |
| **Задание 2.3 — Kafka** | Ansible | **Генерирует** манифесты Strimzi+KafkaCluster, коммитит их в `gitops/platform/strimzi/` | Build-time (manifest generator), не runtime |

**Один runtime source of truth — Git.** Ansible используется как генератор конфигов под Kafka (соответствует букве задания 2.3), но не управляет кластером в рантайме. После запуска плейбука изменения подхватывает ArgoCD.

### Топология k3d: 1 server + 2 agents

- **Server** — изолирован taint'ом `node-role.kubernetes.io/control-plane:NoSchedule`, на нём только control-plane (kube-apiserver, etcd, ArgoCD)
- **Agent #1, #2** — workloads; Kafka-брокеры через `podAntiAffinity` разъезжаются по двум нодам
- HPA на микросервисах имеет куда скейлить под нагрузкой Locust
- Cluster Autoscaler работает на agent-пуле (добавляет/удаляет ноды)

### Container Registry — k3d с DNS-именем

**`k3d-registry.localhost:5000`:**
- При создании кластера: `k3d cluster create --registry-create k3d-registry.localhost:5000`
- k3d прописывает hosts во все ноды → pod'ы pull'ят по этому же имени
- С хоста/CI: `docker push k3d-registry.localhost:5000/<svc>:<tag>` резолвится через `127.0.0.1`
- В Helm values: `image.repository: k3d-registry.localhost:5000/<svc>`

### Streamlit frontend — вне mesh

Frontend нужен только для ручной демо и скриншотов:
- Отдельный namespace `frontend` **без istio-injection**
- Доступ — через тот же Istio Gateway (без sidecar на самом pod'е)
- Не участвует в нагрузочном тесте Locust
- Упрощает Cilium NetworkPolicy и Istio config

### Node Autoscaling — полноценная реализация (Задание 1.2)

- **Cluster Autoscaler** с k3d-провайдером (community fork с поддержкой k3d-node API)
- k3d node-pool: `min=2, max=5` agent-нод
- Демонстрация на нагрузке Locust:
  - Pod-pending → CA добавляет agent через `k3d node create`
  - После окончания нагрузки → CA удаляет лишние ноды через `cooldown`
- Метрики CA → Grafana дашборд (количество нод во времени, scale-up/down события)
- В отчёте: сравнение Karpenter vs Cluster Autoscaler (почему CA, а не Karpenter, на k3d)

### HAProxy + Keepalived — реальный failover внутри Docker

VIP на macOS-хост не пробрасывается, но **полноценный VRRP-failover внутри Docker bridge-сети — работает**:

```
                            VIP 172.30.0.100 (внутри docker network)
                                       │
              ┌────────────────────────┴────────────────────────┐
              │ keepalived-master (MASTER, priority=110)        │
              │ haproxy-master ──► k3d-agent-0, k3d-agent-1     │
              └─────────────────────────────────────────────────┘
              ┌─────────────────────────────────────────────────┐
              │ keepalived-backup (BACKUP, priority=100)        │
              │ haproxy-backup ──► k3d-agent-0, k3d-agent-1     │
              └─────────────────────────────────────────────────┘
```

- 2 контейнера keepalived + 2 HAProxy в той же docker network, что и k3d
- Демонстрация failover: `docker stop keepalived-master` → backup поднимает VIP за 1-3 сек
- Проверка: `docker run --rm --network k3d-pi-platform curlimages/curl http://172.30.0.100`
- Скриншоты: логи keepalived + Hubble UI с непрерывным потоком запросов через failover

---

## Фаза 0: Подготовка репозитория и структуры

**Цель:** создать рабочую ветку и каркас директорий для DevOps-артефактов.

### Шаги
- [x] 0.1 Создать ветку `feature/k8s-platform` от `main`
- [x] 0.2 Создать структуру директорий:
  ```
  infrastructure/
    terraform/
      modules/
      environments/local/
    ansible/
      roles/kafka/
      roles/strimzi-operator/
      playbooks/
    scripts/
      bootstrap-k3d.sh
      install-cilium.sh
      install-argocd.sh
  gitops/
    bootstrap/             # корневой App-of-Apps
    platform/              # istio, observability, rate-limit, strimzi
    workloads/             # user/document/embedding/query
  charts/
    user-service/
    document-service/
    embedding-service/
    query-service/
    platform-common/       # секреты, configmap'ы
  observability/
    dashboards/
    alerts/
    otel-collector-config.yaml
  locust/
    locustfile.py
    Dockerfile
  .github/workflows/
    build-and-push.yml
  docs/
    adr/                   # Architecture Decision Records
    runbook.md
    screenshots/
  ```
- [ ] 0.3 Обновить корневой `README.md` секцией «DevOps-фаза» со ссылками *(делать не будем)*
- [ ] 0.4 Создать скрипт-оркестратор `infrastructure/scripts/bootstrap-all.sh` (наполнится в следующих фазах) — единая точка входа для развёртывания всего стека *(пока не наполнен)*
- [x] 0.5 Версии devops-инструментов (k3d, kubectl, helm, terraform, ansible) зафиксировать прямо в bootstrap-скриптах через переменные (`K3D_VERSION=5.x.x` и т.д.). Python-зависимости — в `pyproject.toml` каждого сервиса (уже есть)

---

## Фаза 1: Локальный кластер Kubernetes (Задание 1.1, 1.2)

**Цель:** работающий 2-нодовый k3d-кластер с Cilium и автоскейлером.

### Шаг 1.1 — k3d cluster
- [x] Установить `k3d`, `kubectl`, `helm`, `cilium-cli` *(через brew)*
- [x] Написать `infrastructure/scripts/bootstrap-k3d.sh`:
  - создаёт кластер `pi-platform` с **1 server + 2 agents**
  - отключает встроенный CNI (`--k3s-arg "--flannel-backend=none"`)
  - **НЕ отключает kube-proxy** (kubeProxyReplacement на k3d+Cilium 1.19 нестабилен; см. ADR-002)
  - отключает `traefik` и встроенный network-policy controller
  - регистрирует локальный registry `k3d-registry.localhost:5001` (5000 занят AirPlay)
- [x] Проверить: `kubectl get nodes` показывает 3 ноды в `NotReady` (ждут CNI)

### Шаг 1.2 — Cilium как CNI
- [x] `infrastructure/scripts/install-cilium.sh` — Cilium 1.19.4, `kubeProxyReplacement=false`, `hubble.enabled/relay/ui`, `tls.enabled=false` для локального dev
- [x] `cilium status` → все компоненты OK (cilium DS 3/3, envoy 3/3, operator 1/1, hubble-relay 1/1, hubble-ui 2/2)
- [ ] `cilium hubble port-forward` → проверить UI на :12000 *(не запускали, скрины в Фазу 7)*
- [ ] Скриншот Hubble UI с трафиком *(Фаза 7)*

### Шаг 1.3 — Сетевые политики (eBPF)
- [x] Написать `CiliumNetworkPolicy` для namespace `apps`:
  - `default-deny` — запрет всему трафику по умолчанию
  - `allow-internal` — DNS, внутренний трафик в apps, в platform/kafka, ingress от istio-system
- [x] Положить в `gitops/platform/network-policies/` (ArgoCD App `network-policies`: Synced/Healthy)

### Шаг 1.4 — Автоскейлинг (Задание 1.2: Cluster Autoscaler)
- [x] Karpenter работает только с cloud-провайдерами → на k3d используем **Cluster Autoscaler** *(через chart `autoscaler/cluster-autoscaler` v9.46.0 с провайдером `clusterapi`)*
- [x] Установить CA через Helm — `infrastructure/scripts/install-cluster-autoscaler.sh`
- [x] ServiceAccount + RBAC создаются helm-чартом (`rbac.create=true`)
- [ ] Скейл-ап/даун на k3d не выполнить без CAPD (Cluster API Provider Docker) — компонент задеплоен (replicas=0), обоснование в отчёте
- [ ] **Дополнительно HPA** на микросервисах — будет в Фазе 5 (helm charts) → драйвер для CA под нагрузкой Locust
- [ ] Скриншот: график количества нод и pod'ов в Grafana во время нагрузочного теста *(Фаза 6)*

**Критерий готовности фазы:** кластер работает, Cilium показывает трафик в Hubble, CA реагирует на нагрузку.

---

## Фаза 2: IaC + GitOps (Задание 2.1, 2.2, 2.3)

**Цель:** вся конфигурация описана в Terraform и Git, ArgoCD автоматически синхронизирует.

### Шаг 2.1 — Terraform базовый слой
- [x] `infrastructure/terraform/environments/local/main.tf` — провайдеры `kubernetes`+`helm`, локальный state
- [x] Модуль `modules/namespaces` — 9 ns: apps, platform, kafka, monitoring, istio-system, argocd, cicd, frontend, rate-limit (apps с `istio-injection=enabled`)
- [x] Модуль `modules/service-accounts` — 5 SA в `apps` (user/document/embedding/query/locust) + 1 в `frontend`
- [x] Модуль `modules/secrets` — postgres-credentials, minio-credentials, jwt-secret (из `terraform.tfvars`, gitignored)
- [x] `terraform apply` → **21 ресурс создан**

### Шаг 2.2 — ArgoCD
- [x] Модуль `modules/argocd` — helm chart `argo/argo-cd 7.6.12` (7.7.x ломается на k3d из-за redis-secret-init job)
- [x] Корневой `Application` (App-of-Apps) в `gitops/bootstrap/root-app.yaml` с auto-sync, prune, selfHeal
- [x] В `gitops/apps/` дочерние Applications:
  - [x] `network-policies.yaml` → `gitops/platform/network-policies/` ✅ Synced/Healthy
  - [ ] `strimzi.yaml` → `gitops/platform/strimzi/` ⚠️ в процессе фикса (выношу strimzi-operator в bootstrap/)
  - [ ] `istio.yaml`, `observability.yaml`, `rate-limit.yaml`, `workloads.yaml` — будут в Фазах 3/4/5
- [x] Применить root-app: `kubectl apply -f gitops/bootstrap/root-app.yaml`
- [ ] Скриншот ArgoCD UI со всеми Healthy/Synced *(Фаза 7)*

### Шаг 2.3 — Ansible Role для Kafka (Strimzi)
- [x] `infrastructure/ansible/roles/strimzi-operator/` — defaults+tasks+templates, генерирует ArgoCD Application для Strimzi через OCI helm chart `oci://quay.io/strimzi-helm`
- [x] `infrastructure/ansible/roles/kafka/` — defaults+tasks+templates `kafka-cluster.yaml.j2` (KafkaNodePool + Kafka KRaft) и `kafka-topics.yaml.j2` (топики `document.uploaded`, `embedding.completed`)
- [x] Playbook `playbooks/deploy-kafka.yml`
- [x] Запуск: `ansible-playbook playbooks/deploy-kafka.yml` — манифесты сгенерированы
- [ ] Проверить: `kubectl -n kafka get kafka,kafkatopic` → Ready *(в процессе: исправление App-of-Apps структуры под sync-wave)*

**Критерий готовности:** в ArgoCD UI видны все Applications со статусом Synced/Healthy, Kafka брокеры работают.

---

## Фаза 3: Ядро и трафик (Задание 3.1, 3.2, 3.3)

**Цель:** Service Mesh с Circuit Breaker и Rate Limiter перед сервисами.

### Шаг 3.1 — Istio
- [ ] Установить Istio через `istio-base`, `istiod`, `istio-ingress` Helm-чарты (положить в `gitops/platform/istio/`)
- [ ] Включить sidecar-injection: `kubectl label ns apps istio-injection=enabled`
- [ ] Для каждого сервиса в `charts/<svc>/templates/` создать:
  - `VirtualService`: HTTP-маршруты с `retries: { attempts: 3, perTryTimeout: 2s, retryOn: 5xx,reset }`
  - `DestinationRule`: `connectionPool` + `outlierDetection: { consecutive5xxErrors: 3, interval: 10s, baseEjectionTime: 30s }`
- [ ] Скриншот Kiali (если устанавливаем) или `kubectl get vs,dr -n apps`

### Шаг 3.2 — Ingress + HAProxy + Keepalived
- [ ] Istio IngressGateway: настроить `Gateway` CR на портах 80/443
- [ ] **HAProxy** перед двумя нодами k3d:
  - `infrastructure/scripts/setup-haproxy.sh` (запускает HAProxy в Docker)
  - `haproxy.cfg`: balance roundrobin между `node-0:80` и `node-1:80`
- [ ] **Keepalived VIP** — на macOS нативно не работает (нужны RAW-сокеты Linux). В отчёте:
  - схема `client → VIP (192.168.x.x) → keepalived(MASTER/BACKUP) → HAProxy → Istio`
  - конфиг `keepalived.conf` (тоже коммитим)
  - обоснование: на ноуте не воспроизводимо, реализуемо в prod
- [ ] Проверить: `curl http://localhost/auth/me` → 401 (значит трафик дошёл до user-service)

### Шаг 3.3 — Rate Limiting (Envoy + Valkey)
- [ ] Развернуть Envoy Rate Limit Service из `envoyproxy/ratelimit`:
  - `gitops/platform/rate-limit/deployment.yaml`
  - ConfigMap с правилами:
    - `/query`: 10 rps на client IP, burst 5
    - `/documents`: 30 rpm на client IP
- [ ] Указать Valkey (уже есть в `apps`) как backend для счётчиков
- [ ] `EnvoyFilter` на Istio IngressGateway: маршрутизация запросов в RLS
- [ ] e2e-проверка: `for i in $(seq 1 20); do curl /query; done` → видим 429 после 10-го запроса

**Критерий готовности:** при отказе сервиса Istio дропает запросы через 3 ошибки; rate limiter возвращает 429; трафик идёт через HAProxy.

---

## Фаза 4: Observability (Часть 4)

**Цель:** единый стек метрик/логов/трейсов с алертами.

### Шаг 4.1 — Выбор стека (обоснование в отчёте)
В `docs/adr/004-observability-stack.md` сравнить 3 варианта:

| Критерий | Loki + Prom + Tempo + Grafana | VictoriaMetrics + VictoriaLogs + Tempo + Grafana | ELK + Jaeger |
|---|---|---|---|
| Память | ~3 ГБ | ~1.5 ГБ | ~6+ ГБ |
| Запросы | LogQL/PromQL | LogsQL/MetricsQL (PromQL-compat) | KQL/Lucene |
| Сложность | средняя | низкая | высокая |

**Выбор:** **VictoriaMetrics + VictoriaLogs + Tempo + Grafana + OTel Collector** (баланс памяти и функционала).

### Шаг 4.2 — Деплой стека
- [ ] `gitops/platform/observability/`:
  - `victoria-metrics-cluster.yaml` (vmstorage + vminsert + vmselect)
  - `victoria-logs.yaml`
  - `tempo.yaml` (single binary mode)
  - `grafana.yaml` с pre-configured datasources
  - `otel-collector.yaml` (receivers: otlp, prometheus; exporters: vmagent, victorialogs, tempo)
  - `vmagent.yaml` (scrape всех сервисов)
  - `alertmanager.yaml`
  - `vmalert.yaml` (правила алертов)

### Шаг 4.3 — Инструментация микросервисов
- [ ] В каждый FastAPI-сервис добавить:
  - `opentelemetry-instrumentation-fastapi` (трейсы)
  - `prometheus-fastapi-instrumentator` (метрики на `/metrics`)
  - `structlog` или `python-json-logger` (JSON-логи → stdout → OTel Collector)
- [ ] Прокинуть переменные `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317`

### Шаг 4.4 — Дашборды Grafana
В `observability/dashboards/`:
- [ ] `kafka.json`: consumer lag, throughput, broker disk usage (из Strimzi exporter)
- [ ] `microservices.json`: RED-метрики (Rate, Errors, Duration) p50/p95/p99 на каждый эндпоинт
- [ ] `istio.json`: success rate, latency между сервисами, outlier-ejections
- [ ] `rate-limit.json`: количество 429, top IP, остаток квоты
- [ ] `infra.json`: Postgres connections, Valkey memory, Qdrant disk, MinIO usage

### Шаг 4.5 — Алерты
В `observability/alerts/rules.yaml`:
- [ ] `HighQueryLatency`: p95 `/query` > 5s 5 минут
- [ ] `KafkaConsumerLag`: lag > 1000 5 минут
- [ ] `RateLimitTriggered`: > 100 событий 429 за минуту
- [ ] `ServiceDown`: probe `up == 0` 2 минуты
- [ ] `CircuitBreakerOpen`: `istio_request_total{response_code=~"5.."}` resets > 5 за 30с

**Критерий готовности:** в Grafana видны все 5 дашбордов с реальными данными; алерты срабатывают при искусственной деградации.

> **AI-monitoring** (k8sgpt, RobustaAI и т.п.) задание помечает как «опционально» — в эту фазу не включаем, в отчёте укажем как возможное расширение для prod.

---

## Фаза 5: CI/CD (Задание 5.1, 5.2, 5.3)

**Цель:** при пуше в Git собирается образ, обновляется Helm-чарт, ArgoCD деплоит.

### Шаг 5.1 — GitHub Actions Self-Hosted Runner
- [ ] Установить `actions-runner-controller` (ARC) в ns `cicd` через Helm
- [ ] Создать GitHub App для аутентификации (или PAT)
- [ ] `RunnerDeployment` с автоскейлом (1-5 раннеров)
- [ ] Проверить: `gh workflow run ping.yml` → раннер подхватил job

### Шаг 5.2 — Локальный Docker Registry
- [ ] k3d уже создал registry на `localhost:5000` (Фаза 1)
- [ ] Альтернативно: Harbor в кластере (`gitops/platform/harbor/`) — для отчёта, не обязательно

### Шаг 5.3 — Helm-чарты
Для каждого из 4 сервисов в `charts/<svc>/`:
- [ ] `Chart.yaml` (version: 0.1.0, appVersion: динамически из CI)
- [ ] `values.yaml`: image.repo/tag, replicas, resources, env (Kafka brokers, Valkey URL, Postgres DSN, MinIO, Qdrant)
- [ ] `templates/`:
  - `deployment.yaml` с health/readiness probes, resource limits
  - `service.yaml` (ClusterIP)
  - `serviceaccount.yaml`
  - `configmap.yaml` (non-secret env)
  - `virtualservice.yaml` + `destinationrule.yaml` (Istio)
  - `servicemonitor.yaml` или OTel-аннотации
- [ ] `charts/platform-common/`: общие секреты, общие configmaps, sealed-secrets (опционально)

### Шаг 5.4 — Pipeline
`.github/workflows/build-and-push.yml`:
- [ ] Триггер: push в `main`, paths `services/**`
- [ ] Job `detect-changes`: определяет изменённые сервисы (path-filter action)
- [ ] Job `build` (matrix по сервисам):
  - Запуск в self-hosted runner
  - **Kaniko**-pod собирает образ → push в `registry.local:5000/<svc>:${{ github.sha }}`
- [ ] Job `update-helm`:
  - `sed`/`yq` меняет `image.tag` в `charts/<svc>/values.yaml`
  - `git commit -m "ci: bump <svc> to ${sha}" && git push`
- [ ] ArgoCD засекает изменение values.yaml → auto-sync → новый Deployment

### Шаг 5.5 — e2e-проверка пайплайна
- [ ] Внести правку в `services/query-service/app/main.py` (например, изменить версию в `/health`)
- [ ] git push → дождаться нового pod'а в кластере → проверить `curl /query/health`

**Критерий готовности:** один git-push в main приводит к развёртыванию новой версии сервиса без ручных действий.

---

## Фаза 6: Тестирование и валидация (Задание 6.1, 6.2, 6.3)

**Цель:** доказать, что платформа выдерживает нагрузку и корректно реагирует на отказы.

### Шаг 6.1 — Locust сценарий
- [ ] `locust/locustfile.py`:
  - `UserBehavior`:
    - on_start: register + login → сохранить JWT
    - task(3): GET /documents
    - task(5): POST /query (вопросы из заранее загруженных документов)
    - task(1): POST /documents (загрузка случайного TXT)
  - `host = http://<haproxy-vip>/`
- [ ] Dockerfile + Helm-чарт для запуска Locust в кластере (`gitops/workloads/locust/`)
- [ ] Запуск: 50 users, ramp-up 1/s, duration 5 min
- [ ] Сохранить отчёт Locust → `docs/screenshots/locust-baseline.html`

### Шаг 6.2 — Chaos: проверка Circuit Breaker
- [ ] Во время нагрузочного теста: `kubectl -n apps scale deployment query-service --replicas=0`
- [ ] Ожидаем:
  - Istio outlier-detection помечает endpoint'ы как unhealthy
  - VirtualService retries срабатывают
  - В Hubble UI / Kiali видим красные стрелки
  - В Grafana `istio.json` видим всплеск 5xx, затем падение запросов к сервису
- [ ] Восстановить: `kubectl scale deployment query-service --replicas=2` → проверить recovery
- [ ] Скриншоты до/во время/после

### Шаг 6.3 — Валидация дашбордов
- [ ] **kafka.json**: видна consumer lag по топику `document.uploaded` (растёт при отключении embedding-service, спадает после восстановления)
- [ ] **rate-limit.json**: видны 429 в момент превышения 10 rps на `/query`
- [ ] **microservices.json**: латентность p95 `/query` в норме (< 3s), всплеск при chaos
- [ ] **istio.json**: success rate упал, outlier-ejections > 0
- [ ] Скриншоты всех дашбордов под нагрузкой → `docs/screenshots/`

**Критерий готовности:** все три проверки выполнены, скриншоты собраны, поведение системы соответствует ожиданиям.

---

## Фаза 7: Отчёт и сравнительный анализ

**Цель:** дополнить `report.md` разделами по DevOps-фазе.

### Структура нового раздела в report.md
- [ ] **Часть 1.** Архитектура кластера: схема k3d + Cilium + CA, обоснование выбора k3d vs Minikube vs Talos
- [ ] **Часть 2.** IaC + GitOps:
  - Terraform-граф зависимостей
  - Схема ArgoCD App-of-Apps
  - Ansible Role design (idempotency, tags)
- [ ] **Часть 3.** Service Mesh:
  - Сравнение Istio vs Linkerd (память, фичи, кривая обучения)
  - Конфиги VirtualService/DestinationRule
  - Схема Ingress: client → Keepalived VIP → HAProxy → Istio Gateway
- [ ] **Часть 4.** Observability:
  - **Большой сравнительный раздел** (3 стека: Loki/VM/ELK) с таблицей и финальным выбором
  - Скриншоты Grafana
  - Список алертов и их пороги
- [ ] **Часть 5.** CI/CD:
  - Сравнение GitLab Runner vs GitHub Actions self-hosted (память, фичи)
  - Schema пайплайна с временными метками
  - Список Helm-чартов
- [ ] **Часть 6.** Тестирование:
  - Результаты Locust (RPS, p95, error rate)
  - Поведение Circuit Breaker (скриншоты до/после chaos)
  - Скриншоты валидированных дашбордов

### ADR (Architecture Decision Records) в docs/adr/
- [ ] `001-k8s-distro.md` — почему k3d
- [ ] `002-cni-cilium.md` — почему Cilium
- [ ] `003-gitops-argocd.md` — почему ArgoCD
- [ ] `004-observability-stack.md` — почему VictoriaMetrics
- [ ] `005-service-mesh.md` — почему Istio
- [ ] `006-ci-platform.md` — почему GitHub Actions

### Runbook
- [ ] `docs/runbook.md` — как поднять с нуля одной командой, troubleshooting, известные проблемы

**Критерий готовности:** отчёт самодостаточен — преподаватель может прочитать и понять архитектуру и обоснования без устных пояснений.

---

## Граф зависимостей фаз

```
Фаза 0 → Фаза 1 → Фаза 2 ─┬──→ Фаза 3 ──┐
                          │              ├──→ Фаза 5 ──→ Фаза 6 ──→ Фаза 7
                          └──→ Фаза 4 ──┘
```

- Фаза 4 (Observability) можно начать сразу после Фазы 2 (ArgoCD), параллельно с Фазой 3
- Фаза 6 (тесты) требует всё, кроме Фазы 7

---

## Оценка времени

| Фаза | Часы (фокусной работы) |
|---|---|
| 0. Структура | 0.5 |
| 1. k3d + Cilium | 1.5 |
| 2. Terraform + ArgoCD + Ansible | 3 |
| 3. Istio + Ingress + RateLimit | 3 |
| 4. Observability | 3 |
| 5. CI/CD + Helm | 3 |
| 6. Locust + chaos | 1.5 |
| 7. Отчёт | 2 |
| **Итого** | **~17.5 ч** |

---

## Риски и допущения

| Риск | Митигация |
|---|---|
| Не хватит RAM на 16 ГБ макбуке | Брокер Kafka в 1 экземпляре, observability с пониженными лимитами, отключать Streamlit-frontend при нагрузочных тестах |
| Cilium на k3d может конфликтовать с Docker Desktop сетью | Использовать `--host-loopback` и фиксированный CIDR в bootstrap-скрипте |
| Istio sidecar добавит ~100MB на pod | Использовать `ambient mode` если упрёмся в память (но он младше и менее стабилен) |
| ArgoCD не подхватит изменения values.yaml | Использовать `argocd-image-updater` для автоматического обновления тэгов |
| Keepalived не работает на macOS | Описать декларативно, не запускать |

---

## Критерии готовности всего задания (DoD)

- [ ] `make bootstrap` поднимает весь стек с нуля за < 15 минут
- [ ] ArgoCD UI: все Applications Synced/Healthy
- [ ] `test_e2e.py` проходит против Ingress в k8s
- [ ] Locust сценарий выполняется без потери запросов (5xx < 1% в стабильном режиме)
- [ ] Chaos-тест: при kill query-service Circuit Breaker открывается, после восстановления — закрывается
- [ ] Все 5 дашбордов Grafana показывают живые данные
- [ ] `report.md` дополнен разделами по всем 6 частям задания
- [ ] Все коммиты идут через CI, образы из локального registry, ArgoCD автосинк
