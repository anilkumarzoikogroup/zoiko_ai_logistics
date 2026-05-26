resource "google_kms_key_ring" "zoiko" {
  project  = var.project_id
  name     = var.keyring
  location = var.region
}

resource "google_kms_crypto_key" "signing" {
  name            = "zoiko-signing-${var.env}"
  key_ring        = google_kms_key_ring.zoiko.id
  purpose         = "ASYMMETRIC_SIGN"
  rotation_period = "7776000s"  # 90 days

  version_template {
    algorithm        = "EC_SIGN_ED25519"
    protection_level = var.env == "production" ? "HSM" : "SOFTWARE"
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "google_kms_crypto_key" "dek_encrypt" {
  name            = "zoiko-dek-${var.env}"
  key_ring        = google_kms_key_ring.zoiko.id
  purpose         = "ENCRYPT_DECRYPT"
  rotation_period = "7776000s"

  version_template {
    algorithm        = "GOOGLE_SYMMETRIC_ENCRYPTION"
    protection_level = var.env == "production" ? "HSM" : "SOFTWARE"
  }

  lifecycle {
    prevent_destroy = true
  }
}
