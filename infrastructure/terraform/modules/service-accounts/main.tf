# ServiceAccounts для микросервисов и инфраструктурных компонентов.
# Каждый pod бежит под своим SA, что позволит позже навесить
# минимальные RBAC и применять CiliumNetworkPolicy по identity.

variable "service_accounts" {
  type = map(object({
    namespace = string
  }))
  default = {
    user-service       = { namespace = "apps" }
    document-service   = { namespace = "apps" }
    embedding-service  = { namespace = "apps" }
    query-service      = { namespace = "apps" }
    frontend-service   = { namespace = "frontend" }
    locust             = { namespace = "apps" }
  }
}

resource "kubernetes_service_account" "this" {
  for_each = var.service_accounts

  metadata {
    name      = each.key
    namespace = each.value.namespace
    labels = {
      "app.kubernetes.io/name"       = each.key
      "app.kubernetes.io/managed-by" = "terraform"
    }
  }
}

output "names" {
  value = [for sa in kubernetes_service_account.this : "${sa.metadata[0].namespace}/${sa.metadata[0].name}"]
}
