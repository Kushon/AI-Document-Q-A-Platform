#!/usr/bin/env bash
# Создаёт локальный k3d-кластер для платформы PI.
# Топология: 1 server + 2 agents, без встроенного CNI (его заменит Cilium),
# без kube-proxy (его заменяет Cilium), без Traefik (Ingress будет Istio),
# с локальным container registry.

set -euo pipefail

# --- Версии (фиксируем для воспроизводимости) -------------------------------
K3D_VERSION_MIN="5.8.0"
K3S_IMAGE="rancher/k3s:v1.33.6-k3s1"

# --- Параметры кластера -----------------------------------------------------
CLUSTER_NAME="${CLUSTER_NAME:-pi-platform}"
REGISTRY_NAME="${REGISTRY_NAME:-k3d-registry.localhost}"
REGISTRY_PORT="${REGISTRY_PORT:-5001}"  # 5000 занят системным ControlCenter (AirPlay Receiver) на macOS
SERVERS="${SERVERS:-1}"
AGENTS="${AGENTS:-2}"
LB_HTTP_PORT="${LB_HTTP_PORT:-8080}"
LB_HTTPS_PORT="${LB_HTTPS_PORT:-8443}"

# --- Helpers ---------------------------------------------------------------
log()  { printf "\033[1;34m[bootstrap-k3d]\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m[bootstrap-k3d]\033[0m %s\n" "$*" >&2; }
fail() { printf "\033[1;31m[bootstrap-k3d]\033[0m %s\n" "$*" >&2; exit 1; }

require() {
  command -v "$1" >/dev/null 2>&1 || fail "не найдена команда '$1' — установите её"
}

require docker
require k3d
require kubectl

# --- Проверка версии k3d ---------------------------------------------------
k3d_ver="$(k3d version 2>/dev/null | awk '/k3d version/ {print $3}' | tr -d 'v')"
[ -n "$k3d_ver" ] || fail "не удалось определить версию k3d"
log "k3d версия: v${k3d_ver} (минимально требуется v${K3D_VERSION_MIN})"

# --- Идемпотентность: если кластер уже есть — выходим ----------------------
if k3d cluster list "$CLUSTER_NAME" >/dev/null 2>&1; then
  warn "кластер '$CLUSTER_NAME' уже существует — пропускаю создание"
  warn "если нужно пересоздать: k3d cluster delete $CLUSTER_NAME"
  exit 0
fi

# --- Создание кластера -----------------------------------------------------
# Ключевые флаги:
#   --k3s-arg "--flannel-backend=none@server:*"  — отключаем встроенный CNI
#   --k3s-arg "--disable-network-policy@server:*" — отключаем встроенный NP-controller
#   --k3s-arg "--disable=traefik@server:*"       — Ingress будет Istio
#   --registry-create                            — поднимаем локальный registry
#
# ВАЖНО: kube-proxy НЕ отключаем. Cilium kubeProxyReplacement на k3d 1.33 + Cilium 1.19
# нестабильно маршрутизирует ClusterIP (наблюдалось EOF в API server из подов).
# Cilium остаётся как CNI (eBPF datapath, NetworkPolicy, Hubble), а сервисы рулит kube-proxy.
log "создаю кластер '$CLUSTER_NAME' (${SERVERS} server + ${AGENTS} agents)"
k3d cluster create "$CLUSTER_NAME" \
  --image "$K3S_IMAGE" \
  --servers "$SERVERS" \
  --agents "$AGENTS" \
  --registry-create "${REGISTRY_NAME}:0.0.0.0:${REGISTRY_PORT}" \
  --k3s-arg "--flannel-backend=none@server:*" \
  --k3s-arg "--disable-network-policy@server:*" \
  --k3s-arg "--disable=traefik@server:*" \
  --port "${LB_HTTP_PORT}:80@loadbalancer" \
  --port "${LB_HTTPS_PORT}:443@loadbalancer" \
  --wait

# --- Постусловия -----------------------------------------------------------
log "ноды кластера:"
kubectl get nodes -o wide

log "kubeconfig context: $(kubectl config current-context)"
log "локальный registry доступен по: ${REGISTRY_NAME}:${REGISTRY_PORT}"
log "Loadbalancer: http://localhost:${LB_HTTP_PORT}  https://localhost:${LB_HTTPS_PORT}"

# Ноды должны быть NotReady — это нормально, ждут CNI (Cilium)
not_ready=$(kubectl get nodes -o jsonpath='{range .items[*]}{.status.conditions[?(@.type=="Ready")].status}{"\n"}{end}' | grep -c "False" || true)
if [ "$not_ready" -gt 0 ]; then
  log "✓ ${not_ready} ноды в состоянии NotReady — ожидается (нет CNI)"
  log "  следующий шаг: ./infrastructure/scripts/install-cilium.sh"
else
  warn "все ноды Ready — возможно, не отключился встроенный CNI"
fi
