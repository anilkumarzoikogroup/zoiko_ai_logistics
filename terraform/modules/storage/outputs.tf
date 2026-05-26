output "worm_bucket_name" {
  value = google_storage_bucket.worm_audit.name
}
output "worm_bucket_url" {
  value = google_storage_bucket.worm_audit.url
}
