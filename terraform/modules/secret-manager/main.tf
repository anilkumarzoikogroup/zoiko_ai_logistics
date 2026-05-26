resource "google_secret_manager_secret" "db_password" {
  project   = var.project_id
  secret_id = "zoiko-${var.env}-db-password"
  replication { auto {} }
}

resource "google_secret_manager_secret" "dev_secret" {
  project   = var.project_id
  secret_id = "zoiko-${var.env}-dev-secret"
  replication { auto {} }
}

resource "google_secret_manager_secret" "jwt_signing_secret" {
  project   = var.project_id
  secret_id = "zoiko-${var.env}-jwt-signing-secret"
  replication { auto {} }
}
