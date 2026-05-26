# Service account for Cloud Run services
resource "google_service_account" "zoiko_services" {
  project      = var.project_id
  account_id   = "zoiko-svc-${var.env}"
  display_name = "Zoiko Services SA (${var.env})"
}

# KMS sign/verify
resource "google_kms_key_ring_iam_member" "kms_signer" {
  key_ring_id = "projects/${var.project_id}/locations/asia-south1/keyRings/zoiko-${var.env}"
  role        = "roles/cloudkms.signerVerifier"
  member      = "serviceAccount:${google_service_account.zoiko_services.email}"
}

# Cloud SQL access
resource "google_project_iam_member" "sql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.zoiko_services.email}"
}

# Secret Manager accessor
resource "google_project_iam_member" "secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.zoiko_services.email}"
}

# Storage object creator (WORM writes)
resource "google_project_iam_member" "storage_creator" {
  project = var.project_id
  role    = "roles/storage.objectCreator"
  member  = "serviceAccount:${google_service_account.zoiko_services.email}"
}
