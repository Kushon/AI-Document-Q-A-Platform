# Namespaces для платформы PI.
# Лейблы используются для:
#   - istio-injection (включаем sidecar-инжекцию там, где нужно)
#   - app.kubernetes.io/managed-by (трейсинг)

variable "namespaces" {
  type = map(object({
    istio_injection = bool
    labels          = map(string)
  }))
  default = {
    apps = {
      istio_injection = true
      labels          = { "purpose" = "microservices" }
    }
    platform = {
      istio_injection = false
      labels          = { "purpose" = "infrastructure" }  # postgres, valkey, qdrant, minio
    }
    kafka = {
      istio_injection = false
      labels          = { "purpose" = "messaging" }       # Strimzi + KafkaCluster
    }
    monitoring = {
      istio_injection = false
      labels          = { "purpose" = "observability" }
    }
    "istio-system" = {
      istio_injection = false
      labels          = { "purpose" = "service-mesh" }
    }
    argocd = {
      istio_injection = false
      labels          = { "purpose" = "gitops" }
    }
    cicd = {
      istio_injection = false
      labels          = { "purpose" = "ci-runner" }
    }
    frontend = {
      istio_injection = false                              # frontend вне mesh
      labels          = { "purpose" = "frontend" }
    }
    "rate-limit" = {
      istio_injection = false
      labels          = { "purpose" = "ratelimit" }
    }
  }
}

resource "kubernetes_namespace" "this" {
  for_each = var.namespaces

  metadata {
    name = each.key
    labels = merge(
      each.value.labels,
      {
        "app.kubernetes.io/managed-by" = "terraform"
        "istio-injection"              = each.value.istio_injection ? "enabled" : "disabled"
      }
    )
  }
}

output "names" {
  value = [for ns in kubernetes_namespace.this : ns.metadata[0].name]
}
