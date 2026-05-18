# Базовые секреты платформы.
# В проде эти значения должны приходить из Vault/SOPS/External-Secrets;
# для локальной разработки они задаются в terraform.tfvars (gitignored).

variable "postgres" {
  type = object({
    username = string
    password = string
    database = string
  })
  sensitive = true
}

variable "minio" {
  type = object({
    access_key = string
    secret_key = string
  })
  sensitive = true
}

variable "jwt_secret" {
  type      = string
  sensitive = true
}

variable "apps_namespace" {
  type    = string
  default = "apps"
}

variable "platform_namespace" {
  type    = string
  default = "platform"
}

# --- Postgres ---------------------------------------------------------------
resource "kubernetes_secret" "postgres" {
  metadata {
    name      = "postgres-credentials"
    namespace = var.platform_namespace
    labels    = { "app.kubernetes.io/managed-by" = "terraform" }
  }
  type = "Opaque"
  data = {
    POSTGRES_USER     = var.postgres.username
    POSTGRES_PASSWORD = var.postgres.password
    POSTGRES_DB       = var.postgres.database
  }
}

# Тот же секрет нужен микросервисам в namespace 'apps' для подключения
resource "kubernetes_secret" "postgres_apps" {
  metadata {
    name      = "postgres-credentials"
    namespace = var.apps_namespace
    labels    = { "app.kubernetes.io/managed-by" = "terraform" }
  }
  type = "Opaque"
  data = {
    POSTGRES_USER     = var.postgres.username
    POSTGRES_PASSWORD = var.postgres.password
    POSTGRES_DB       = var.postgres.database
    POSTGRES_DSN      = "postgresql+asyncpg://${var.postgres.username}:${var.postgres.password}@postgres.platform.svc.cluster.local:5432/${var.postgres.database}"
  }
}

# --- MinIO -----------------------------------------------------------------
resource "kubernetes_secret" "minio" {
  metadata {
    name      = "minio-credentials"
    namespace = var.platform_namespace
    labels    = { "app.kubernetes.io/managed-by" = "terraform" }
  }
  type = "Opaque"
  data = {
    MINIO_ROOT_USER     = var.minio.access_key
    MINIO_ROOT_PASSWORD = var.minio.secret_key
  }
}

resource "kubernetes_secret" "minio_apps" {
  metadata {
    name      = "minio-credentials"
    namespace = var.apps_namespace
    labels    = { "app.kubernetes.io/managed-by" = "terraform" }
  }
  type = "Opaque"
  data = {
    MINIO_ACCESS_KEY = var.minio.access_key
    MINIO_SECRET_KEY = var.minio.secret_key
    MINIO_ENDPOINT   = "minio.platform.svc.cluster.local:9000"
  }
}

# --- JWT (для user-service и query-service) -------------------------------
resource "kubernetes_secret" "jwt" {
  metadata {
    name      = "jwt-secret"
    namespace = var.apps_namespace
    labels    = { "app.kubernetes.io/managed-by" = "terraform" }
  }
  type = "Opaque"
  data = {
    JWT_SECRET    = var.jwt_secret
    JWT_ALGORITHM = "HS256"
  }
}
