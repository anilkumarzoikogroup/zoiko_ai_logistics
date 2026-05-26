resource "google_redis_instance" "zoiko" {
  project        = var.project_id
  name           = "zoiko-${var.env}"
  tier           = var.tier
  memory_size_gb = var.env == "production" ? 4 : 1
  region         = var.region
  redis_version  = "REDIS_7_0"
  authorized_network = var.network_self_link

  auth_enabled            = true
  transit_encryption_mode = "SERVER_AUTHENTICATION"

  maintenance_policy {
    weekly_maintenance_window {
      day = "SUNDAY"
      start_time { hours = 2; minutes = 0; seconds = 0; nanos = 0 }
    }
  }
}
