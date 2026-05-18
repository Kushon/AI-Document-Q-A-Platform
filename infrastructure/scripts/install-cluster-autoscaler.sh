#!/usr/bin/env bash
# Устанавливает Cluster Autoscaler (Задание 1.2).
#
# Важно про k3d: у Cluster Autoscaler нет нативного "cloud provider" для k3d.
# Мы устанавливаем CA с провайдером clusterapi (без CAPD) — это разворачивает
# компонент в кластере, RBAC настроен, метрики /metrics доступны.
# Реальный scale-up/down нод требует:
#   - в проде: cloud-провайдер (AWS/Azure/GCP) или CAPI + CAPD
#   - локально: HPA на микросервисах (см. Фазу 5) + ручное добавление через
#     `k3d node create --cluster pi-platform` для демонстрации
#
# В отчёте мы фиксируем архитектуру и обоснование (Karpenter — только cloud,
# поэтому CA), а под нагрузкой Locust HPA реально скейлит pod'ы.

set -euo pipefail

CA_VERSION="${CA_VERSION:-9.46.0}"  # chart version
CLUSTER_NAME="${CLUSTER_NAME:-pi-platform}"

log()  { printf "\033[1;34m[cluster-autoscaler]\033[0m %s\n" "$*"; }
fail() { printf "\033[1;31m[cluster-autoscaler]\033[0m %s\n" "$*" >&2; exit 1; }

command -v helm >/dev/null 2>&1 || fail "не найден helm"
command -v kubectl >/dev/null 2>&1 || fail "не найден kubectl"

ctx="$(kubectl config current-context 2>/dev/null || true)"
[[ "$ctx" == "k3d-${CLUSTER_NAME}" ]] || \
  fail "kubectl context = '$ctx', ожидался 'k3d-${CLUSTER_NAME}'"

log "добавляю helm repo autoscaler"
helm repo add autoscaler https://kubernetes.github.io/autoscaler >/dev/null 2>&1 || true
helm repo update autoscaler >/dev/null

log "устанавливаю cluster-autoscaler (chart v${CA_VERSION})"
helm upgrade --install cluster-autoscaler autoscaler/cluster-autoscaler \
  --version "${CA_VERSION}" \
  -n kube-system \
  --set cloudProvider=clusterapi \
  --set autoDiscovery.clusterName="${CLUSTER_NAME}" \
  --set "extraArgs.scale-down-delay-after-add=2m" \
  --set "extraArgs.scale-down-unneeded-time=3m" \
  --set "extraArgs.skip-nodes-with-local-storage=false" \
  --set "extraArgs.skip-nodes-with-system-pods=false" \
  --set "extraArgs.scan-interval=30s" \
  --set rbac.create=true \
  --set rbac.serviceAccount.create=true \
  --wait --timeout 3m

log "статус:"
kubectl -n kube-system get deployment -l app.kubernetes.io/name=clusterapi-cluster-autoscaler
kubectl -n kube-system get pods -l app.kubernetes.io/name=clusterapi-cluster-autoscaler

cat <<EOF

✓ Cluster Autoscaler установлен.

Проверка:
  kubectl -n kube-system logs -l app.kubernetes.io/name=clusterapi-cluster-autoscaler --tail=20

Для реальной демонстрации скейл-апа на k3d используется:
  - HPA на микросервисах (Фаза 5) — скейл pod'ов под нагрузкой
  - k3d node create k3d-pi-platform-agent-2 --cluster pi-platform — ручное добавление ноды
EOF
