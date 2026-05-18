#!/usr/bin/env bash
# Задание 6.2 — проверка срабатывания Istio Circuit Breaker
# во время нагрузочного тестирования Locust.
#
# Сценарий:
#   1. Стартуем Locust headless: 50 users, ramp-up 1/sec, duration 5 min,
#      отчёт в docs/screenshots/locust-chaos.html
#   2. Через 60 сек "роняем" query-service: scale --replicas=0
#   3. Ещё через 60 сек восстанавливаем: scale --replicas=2
#   4. Locust продолжает крутиться, в отчёте видно: всплеск 5xx → стабилизация
#      → восстановление. В Grafana istio.json — Circuit Breaker открыт →
#      outlier-detection ejection → закрытие.
#
# Что должно произойти:
#   - retry policy в VirtualService: 3 попытки → пользователь получит 5xx после 3
#   - outlierDetection: 3 ошибки 5xx подряд → endpoint исключён на 30s
#   - После восстановления pod-ов CB сам "закрывается" по интервалу
#
# Требуется: Locust установлен (pip install locust) ИЛИ
#            docker и образ locustio/locust
set -euo pipefail

HOST="${HOST:-http://172.30.0.100}"   # VIP HAProxy в docker network k3d-pi-platform
USERS="${USERS:-50}"
DURATION="${DURATION:-5m}"
SCREEN_DIR="${SCREEN_DIR:-$(pwd)/../docs/screenshots}"

log() { printf "\033[1;34m[chaos]\033[0m %s\n" "$*"; }

mkdir -p "$SCREEN_DIR"

log "1. Запускаю Locust в background (host=$HOST, users=$USERS, time=$DURATION)"
locust --headless \
  -u "$USERS" -r 1 -t "$DURATION" \
  --host="$HOST" \
  --html "$SCREEN_DIR/locust-chaos.html" \
  -f "$(dirname "$0")/locustfile.py" \
  > /tmp/locust.log 2>&1 &
LOCUST_PID=$!

log "2. Жду 60 сек чтобы накопить baseline-трафик"
sleep 60

log "3. KILL: scale deployment query-service --replicas=0 (Circuit Breaker должен открыться)"
kubectl -n apps scale deployment query-service --replicas=0
log "   ожидаемая реакция: VS retry (3 попытки) → 5xx → outlierDetection ejection"

sleep 60

log "4. Сохраняю снимок Grafana state до восстановления:"
log "   - перед восстановлением сделайте скриншот istio.json + rate-limit.json"

log "5. RESTORE: scale deployment query-service --replicas=2"
kubectl -n apps scale deployment query-service --replicas=2
log "   ожидаемая реакция: новые pods Ready → CB закрывается → 5xx падает"

log "6. Жду пока Locust завершится"
wait $LOCUST_PID || true

log "7. Отчёт Locust: $SCREEN_DIR/locust-chaos.html"
log "8. Скриншоты Grafana — Задание 6.3 — снимать вручную после теста"
