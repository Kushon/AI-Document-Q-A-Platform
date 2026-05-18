# Переменные для локального окружения.
# Значения задаются в terraform.tfvars (gitignored).
# Для CI/CD передаются через -var или TF_VAR_*.

variable "postgres_username" {
  type    = string
  default = "rag"
}

variable "postgres_password" {
  type      = string
  sensitive = true
}

variable "postgres_database" {
  type    = string
  default = "ragdb"
}

variable "minio_access_key" {
  type      = string
  sensitive = true
  default   = "minioadmin"
}

variable "minio_secret_key" {
  type      = string
  sensitive = true
}

variable "jwt_secret" {
  type      = string
  sensitive = true
}
