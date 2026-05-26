output "host"      { value = google_redis_instance.zoiko.host }
output "port"      { value = google_redis_instance.zoiko.port }
output "auth_string" { value = google_redis_instance.zoiko.auth_string; sensitive = true }
