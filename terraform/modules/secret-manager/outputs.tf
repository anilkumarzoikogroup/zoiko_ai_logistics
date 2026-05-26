output "db_password_secret"     { value = google_secret_manager_secret.db_password.secret_id }
output "dev_secret_name"        { value = google_secret_manager_secret.dev_secret.secret_id }
output "jwt_signing_secret_name"{ value = google_secret_manager_secret.jwt_signing_secret.secret_id }
