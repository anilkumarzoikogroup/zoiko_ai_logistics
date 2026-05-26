resource "google_sql_database_instance" "zoiko" {
  project          = var.project_id
  name             = "zoiko-${var.env}"
  database_version = "POSTGRES_15"
  region           = var.region

  settings {
    tier              = var.db_tier
    availability_type = var.env == "production" ? "REGIONAL" : "ZONAL"
    disk_size         = 20
    disk_autoresize   = true

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
      transaction_log_retention_days = 7
      backup_retention_settings {
        retained_backups = 14
      }
    }

    ip_configuration {
      ipv4_enabled    = false
      private_network = var.network_self_link
      require_ssl     = true
    }

    database_flags {
      name  = "log_checkpoints"
      value = "on"
    }
    database_flags {
      name  = "log_connections"
      value = "on"
    }
  }

  deletion_protection = var.env == "production" ? true : false
}

resource "google_sql_database" "zoiko" {
  project  = var.project_id
  name     = var.db_name
  instance = google_sql_database_instance.zoiko.name
}

resource "google_sql_user" "app" {
  project  = var.project_id
  name     = "zoiko_app"
  instance = google_sql_database_instance.zoiko.name
  password = random_password.db_password.result
}

resource "random_password" "db_password" {
  length  = 32
  special = true
}
