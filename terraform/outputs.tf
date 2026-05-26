output "phase2_api_url" {
  description = "Phase 2 API gateway Cloud Run URL"
  value       = module.cloud_run.phase2_url
}

output "phase4_api_url" {
  description = "Phase 4 execution gateway Cloud Run URL"
  value       = module.cloud_run.phase4_url
}

output "connector_hub_url" {
  description = "Connector Hub Cloud Run URL"
  value       = module.cloud_run.connector_hub_url
}

output "db_connection_name" {
  description = "Cloud SQL connection name"
  value       = module.cloud_sql.connection_name
}

output "worm_bucket_name" {
  description = "WORM audit bucket name"
  value       = module.storage.worm_bucket_name
}

output "kms_signing_key" {
  description = "KMS signing key resource name"
  value       = module.kms.signing_key_name
}
