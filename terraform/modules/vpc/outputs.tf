output "network_self_link" {
  value = google_compute_network.zoiko.self_link
}
output "subnet_self_link" {
  value = google_compute_subnetwork.services.self_link
}
