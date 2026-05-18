# Bootstrap-слой кластера pi-platform (k3d).
# Этот terraform создаёт ТОЛЬКО то, что нужно до запуска ArgoCD:
#   - namespaces
#   - service accounts
#   - базовые secrets
#   - ArgoCD сам
# Дальнейшие приложения (Istio, Strimzi, observability, микросервисы)
# деплоит ArgoCD через App-of-Apps из gitops/.

module "namespaces" {
  source = "../../modules/namespaces"
}

module "service_accounts" {
  source     = "../../modules/service-accounts"
  depends_on = [module.namespaces]
}

module "secrets" {
  source     = "../../modules/secrets"
  depends_on = [module.namespaces]

  postgres = {
    username = var.postgres_username
    password = var.postgres_password
    database = var.postgres_database
  }
  minio = {
    access_key = var.minio_access_key
    secret_key = var.minio_secret_key
  }
  jwt_secret = var.jwt_secret
}

module "argocd" {
  source     = "../../modules/argocd"
  depends_on = [module.namespaces]
}

output "namespaces" {
  value = module.namespaces.names
}

output "service_accounts" {
  value = module.service_accounts.names
}

output "argocd_admin_password" {
  value = module.argocd.initial_admin_password_hint
}

output "argocd_port_forward" {
  value = module.argocd.port_forward_hint
}
