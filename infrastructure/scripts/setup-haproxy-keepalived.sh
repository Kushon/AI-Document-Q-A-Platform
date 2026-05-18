#!/usr/bin/env bash
# Поднимает в docker network k3d-pi-platform пару HAProxy+Keepalived
# для демонстрации VIP-failover (Задание 3.2).
#
# Архитектура:
#   client (curl-контейнер в той же сети)
#       │
#       ▼ VIP 172.30.0.100
#   ┌───────────────────────────────┐
#   │ keepalived-master (priority=110, MASTER)
#   │   ↳ HAProxy → istio-ingressgateway.istio-system.svc.cluster.local
#   ├───────────────────────────────┤
#   │ keepalived-backup (priority=100, BACKUP)
#   │   ↳ HAProxy → istio-ingressgateway
#   └───────────────────────────────┘
#
# Демонстрация failover:
#   docker stop keepalived-master  → backup забирает VIP за 1-3 сек

set -euo pipefail

CLUSTER_NAME="${CLUSTER_NAME:-pi-platform}"
NETWORK="k3d-${CLUSTER_NAME}"
VIP="${VIP:-172.30.0.100}"
HAPROXY_IMG="haproxytech/haproxy-alpine:2.9"
KEEPALIVED_IMG="osixia/keepalived:2.0.20"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONF_DIR="${SCRIPT_DIR}/haproxy-keepalived-conf"

log()  { printf "\033[1;34m[haproxy-keepalived]\033[0m %s\n" "$*"; }
fail() { printf "\033[1;31m[haproxy-keepalived]\033[0m %s\n" "$*" >&2; exit 1; }

# --- проверки --------------------------------------------------------------
docker network inspect "$NETWORK" >/dev/null 2>&1 \
  || fail "docker network '$NETWORK' не найдена — создайте k3d-кластер"

# --- HAProxy конфиг (одинаковый для обоих instance) ------------------------
mkdir -p "$CONF_DIR"
cat > "$CONF_DIR/haproxy.cfg" <<'EOF'
global
  daemon
  log stdout format raw local0
  maxconn 4096

defaults
  log     global
  mode    http
  option  httplog
  timeout connect 5s
  timeout client  30s
  timeout server  30s
  option  forwardfor

frontend http-in
  bind *:80
  default_backend istio-gw

# istio-ingressgateway DNS работает только из cluster pod'ов.
# Из docker network используем имена k3d-агент-нод (на них kube-proxy
# открывает NodePort через iptables к istio-ingressgateway ClusterIP).
backend istio-gw
  balance roundrobin
  option httpchk GET /healthz/ready
  server agent-0 k3d-pi-platform-agent-0:30080 check
  server agent-1 k3d-pi-platform-agent-1:30080 check
EOF

# --- Keepalived конфиги (master / backup) ----------------------------------
cat > "$CONF_DIR/keepalived-master.conf" <<EOF
vrrp_instance VI_1 {
  state MASTER
  interface eth0
  virtual_router_id 51
  priority 110
  advert_int 1
  authentication { auth_type PASS; auth_pass pi2026 }
  virtual_ipaddress { ${VIP}/24 }
  track_script { chk_haproxy }
}
vrrp_script chk_haproxy {
  script "pidof haproxy || exit 1"
  interval 2
  weight 2
}
EOF
sed 's/state MASTER/state BACKUP/; s/priority 110/priority 100/' \
    "$CONF_DIR/keepalived-master.conf" > "$CONF_DIR/keepalived-backup.conf"

# --- helper: запуск одного instance ---------------------------------------
run_pair() {
  local name="$1"
  local kp_conf="$2"

  log "запуск haproxy-${name}"
  docker rm -f "haproxy-${name}" >/dev/null 2>&1 || true
  docker run -d --name "haproxy-${name}" \
    --network "$NETWORK" \
    -v "$CONF_DIR/haproxy.cfg:/usr/local/etc/haproxy/haproxy.cfg:ro" \
    "$HAPROXY_IMG"

  log "запуск keepalived-${name}"
  docker rm -f "keepalived-${name}" >/dev/null 2>&1 || true
  docker run -d --name "keepalived-${name}" \
    --network "$NETWORK" \
    --cap-add NET_ADMIN --cap-add NET_BROADCAST --cap-add NET_RAW \
    -v "${CONF_DIR}/${kp_conf}:/usr/local/etc/keepalived/keepalived.conf:ro" \
    -e KEEPALIVED_INTERFACE=eth0 \
    "$KEEPALIVED_IMG"
}

run_pair master keepalived-master.conf
run_pair backup keepalived-backup.conf

log "ждём пока VIP появится..."
sleep 5

log "VIP должен быть на keepalived-master:"
docker exec keepalived-master ip -4 addr show eth0 | grep -E "inet " || true

cat <<EOF

✓ HAProxy+Keepalived развёрнуты.

VIP: ${VIP}

Тест извне (из другого контейнера в той же сети):
  docker run --rm --network ${NETWORK} curlimages/curl -s -o /dev/null -w "%{http_code}\n" http://${VIP}/

Тест failover:
  docker stop keepalived-master
  # → backup забирает VIP за 1-3 сек, проверить:
  docker exec keepalived-backup ip -4 addr show eth0 | grep ${VIP}

Восстановить:
  docker start keepalived-master
EOF
