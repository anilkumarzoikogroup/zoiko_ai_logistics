resource "google_compute_network" "zoiko" {
  project                 = var.project_id
  name                    = "zoiko-${var.env}"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "services" {
  project       = var.project_id
  name          = "zoiko-${var.env}-services"
  ip_cidr_range = "10.10.0.0/24"
  region        = var.region
  network       = google_compute_network.zoiko.id

  private_ip_google_access = true
}

resource "google_compute_router" "router" {
  project = var.project_id
  name    = "zoiko-${var.env}-router"
  network = google_compute_network.zoiko.id
  region  = var.region
}

resource "google_compute_router_nat" "nat" {
  project                            = var.project_id
  name                               = "zoiko-${var.env}-nat"
  router                             = google_compute_router.router.name
  region                             = var.region
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"
}
