# ArgoCD через официальный Helm-чарт.
# После установки ArgoCD сам управляет всеми остальными приложениями через
# Application CR (root-app в gitops/bootstrap/).

variable "chart_version" {
  type    = string
  default = "7.6.12"    # argo-cd helm chart (до bump'а в 7.7.x с проблемами redis-secret-init job на k3d)
}

variable "namespace" {
  type    = string
  default = "argocd"
}

# Чарт ArgoCD — минимальные ресурсы под локальный k3d
resource "helm_release" "argocd" {
  name       = "argocd"
  repository = "https://argoproj.github.io/argo-helm"
  chart      = "argo-cd"
  version    = var.chart_version
  namespace  = var.namespace

  # Не создавать namespace — он уже есть (создан модулем namespaces)
  create_namespace = false

  wait    = true
  timeout = 600

  values = [yamlencode({
    global = {
      domain = "argocd.local"
    }
    configs = {
      params = {
        # Доступ к UI без TLS внутри cluster — для локальной dev
        "server.insecure" = true
      }
    }
    server = {
      service = {
        type = "ClusterIP"     # доступ через kubectl port-forward
      }
    }
    # Уменьшаем replicas для локального k3d (по умолчанию HA с 3 реплик)
    controller = {
      replicas = 1
    }
    repoServer = {
      replicas = 1
    }
    applicationSet = {
      replicas = 1
    }
    redis-ha = {
      enabled = false
    }
    redis = {
      enabled = true
    }
  })]
}

output "initial_admin_password_hint" {
  value = "kubectl -n ${var.namespace} get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d"
}

output "port_forward_hint" {
  value = "kubectl -n ${var.namespace} port-forward svc/argocd-server 8090:80  # затем http://localhost:8090 (user: admin)"
}
