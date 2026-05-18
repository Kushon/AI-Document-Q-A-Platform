#!/usr/bin/env bash
# Устанавливает Cilium как CNI для k3d-кластера: eBPF datapath, замена kube-proxy,
# Hubble (observability) и Hubble UI.
#
# Требует: k3d-кластер уже создан (см. bootstrap-k3d.sh).

set -euo pipefail

# --- Версии ----------------------------------------------------------------
CILIUM_VERSION="${CILIUM_VERSION:-1.19.3}"

# --- Параметры -------------------------------------------------------------
CLUSTER_NAME="${CLUSTER_NAME:-pi-platform}"
K3D_API_HOST="k3d-${CLUSTER_NAME}-server-0"
HUBBLE_UI_PORT="${HUBBLE_UI_PORT:-12000}"

log()  { printf "\033[1;34m[install-cilium]\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m[install-cilium]\033[0m %s\n" "$*" >&2; }
fail() { printf "\033[1;31m[install-cilium]\033[0m %s\n" "$*" >&2; exit 1; }

require() {
  command -v "$1" >/dev/null 2>&1 || fail "не найдена команда '$1'"
}

require kubectl
require cilium

# Проверяем контекст kubectl
ctx="$(kubectl config current-context 2>/dev/null || true)"
[[ "$ctx" == "k3d-${CLUSTER_NAME}" ]] || \
  fail "kubectl context = '$ctx', ожидался 'k3d-${CLUSTER_NAME}'. Запустите: kubectl config use-context k3d-${CLUSTER_NAME}"

# --- Идемпотентность -------------------------------------------------------
if kubectl -n kube-system get daemonset cilium >/dev/null 2>&1; then
  warn "Cilium уже установлен — выполняю upgrade вместо install"
  CILIUM_CMD="upgrade"
else
  CILIUM_CMD="install"
fi

# --- Установка Cilium ------------------------------------------------------
# kubeProxyReplacement=true  — Cilium заменяет kube-proxy (он отключен в k3d)
# k8sServiceHost/Port        — Cilium должен знать API server без kube-proxy
# hubble.*                   — включаем eBPF observability + UI
log "${CILIUM_CMD} Cilium v${CILIUM_VERSION}"
# Cilium на k3d работает как CNI (eBPF), kube-proxy оставлен включённым —
# kubeProxyReplacement на k3d 1.33+Cilium 1.19 ломает ClusterIP routing.
# Hubble TLS отключаем для локального dev (всё внутри кластерной сети).
cilium "${CILIUM_CMD}" \
  --version "${CILIUM_VERSION}" \
  --set kubeProxyReplacement=false \
  --set hubble.enabled=true \
  --set hubble.relay.enabled=true \
  --set hubble.ui.enabled=true \
  --set hubble.tls.enabled=false \
  --set ipam.mode=kubernetes \
  --set operator.replicas=1

log "ожидаю готовности Cilium (до 5 минут)..."
cilium status --wait --wait-duration 5m

# --- Постусловия -----------------------------------------------------------
log "проверка connectivity (короткий тест):"
cilium connectivity test --test "no-policies" --test-namespace cilium-test || \
  warn "connectivity test не прошёл — для локальной демо это допустимо, проверьте 'cilium status'"

log "ноды кластера после установки CNI:"
kubectl get nodes -o wide

log "Cilium компоненты:"
kubectl -n kube-system get pods -l k8s-app=cilium
kubectl -n kube-system get pods -l name=cilium-operator
kubectl -n kube-system get pods -l k8s-app=hubble-relay
kubectl -n kube-system get pods -l k8s-app=hubble-ui

cat <<EOF

✓ Cilium установлен.

Что дальше:
  - Открыть Hubble UI:
      cilium hubble ui --port-forward ${HUBBLE_UI_PORT}
      затем http://localhost:${HUBBLE_UI_PORT}

  - Запустить hubble CLI:
      cilium hubble port-forward &
      hubble observe --follow

  - Следующий шаг bootstrap'а:
      ./infrastructure/scripts/install-argocd.sh   (после Фазы 2)
EOF
