# WORM audit bucket — object lock prevents deletion or overwrite.
# is_locked=true in audit_worm_index means the object is immutable.

resource "google_storage_bucket" "worm_audit" {
  project       = var.project_id
  name          = "zoiko-${var.env}-worm-audit"
  location      = var.region
  force_destroy = false   # prevent accidental destruction in prod

  # Object versioning — WORM semantics
  versioning {
    enabled = true
  }

  # Retention policy: 7 years for financial audit records
  retention_policy {
    retention_period = 220752000   # 7 years in seconds
    is_locked        = var.env == "production" ? true : false
  }

  uniform_bucket_level_access = true

  lifecycle_rule {
    action { type = "SetStorageClass"; storage_class = "COLDLINE" }
    condition { age = 365 }
  }
}

resource "google_storage_bucket_iam_binding" "worm_writer" {
  bucket = google_storage_bucket.worm_audit.name
  role   = "roles/storage.objectCreator"
  members = var.writer_service_accounts
}
