output "signing_key_name" {
  value = google_kms_crypto_key.signing.id
}
output "dek_key_name" {
  value = google_kms_crypto_key.dek_encrypt.id
}
output "keyring_name" {
  value = google_kms_key_ring.zoiko.id
}
