terraform {
  required_version = ">= 1.7"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
  # State stored in GCS — bucket created manually before first apply
  backend "gcs" {
    bucket = "zoiko-logistics-dev-tfstate"
    prefix = "terraform/state"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# -----------------------------------------------------------------------
# Variables
# -----------------------------------------------------------------------

variable "project_id" {
  description = "GCP project ID for dev environment"
  type        = string
  default     = "zoiko-logistics-dev"
}

variable "region" {
  description = "Primary GCP region"
  type        = string
  default     = "us-central1"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "dev"
}

# -----------------------------------------------------------------------
# APIs to enable
# -----------------------------------------------------------------------

locals {
  required_apis = [
    "cloudkms.googleapis.com",
    "sqladmin.googleapis.com",
    "redis.googleapis.com",
    "container.googleapis.com",
    "artifactregistry.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "iam.googleapis.com",
    "cloudresourcemanager.googleapis.com",
  ]
}

resource "google_project_service" "apis" {
  for_each           = toset(local.required_apis)
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

# -----------------------------------------------------------------------
# KMS key ring (software keys in dev — P1 adds per-service signing keys)
# -----------------------------------------------------------------------

resource "google_kms_key_ring" "zoiko_dev" {
  name     = "zoiko-dev"
  location = var.region
  project  = var.project_id

  depends_on = [google_project_service.apis]
}

# Root CMK — symmetric encryption, 90-day rotation
resource "google_kms_crypto_key" "root_cmk" {
  name            = "root-cmk"
  key_ring        = google_kms_key_ring.zoiko_dev.id
  rotation_period = "7776000s" # 90 days

  version_template {
    algorithm        = "GOOGLE_SYMMETRIC_ENCRYPTION"
    protection_level = "SOFTWARE" # dev only; staging/prod = HSM
  }

  lifecycle {
    prevent_destroy = true
  }
}

# -----------------------------------------------------------------------
# Cloud SQL (PostgreSQL 15) — dev: single instance, no HA
# -----------------------------------------------------------------------

resource "google_sql_database_instance" "zoiko_dev" {
  name             = "zoiko-dev-pg15"
  database_version = "POSTGRES_15"
  region           = var.region
  project          = var.project_id

  settings {
    tier              = "db-g1-small"
    availability_type = "ZONAL" # dev: single zone; prod: REGIONAL
    disk_autoresize   = true
    disk_size         = 20

    backup_configuration {
      enabled    = true
      start_time = "03:00"
    }

    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.zoiko_vpc.id
    }
  }

  deletion_protection = false # dev only; set true in prod

  depends_on = [google_project_service.apis]
}

resource "google_sql_database" "zoiko" {
  name     = "zoiko"
  instance = google_sql_database_instance.zoiko_dev.name
  project  = var.project_id
}

# -----------------------------------------------------------------------
# VPC network
# -----------------------------------------------------------------------

resource "google_compute_network" "zoiko_vpc" {
  name                    = "zoiko-dev-vpc"
  auto_create_subnetworks = false
  project                 = var.project_id
}

resource "google_compute_subnetwork" "zoiko_subnet" {
  name          = "zoiko-dev-subnet"
  ip_cidr_range = "10.10.0.0/20"
  region        = var.region
  network       = google_compute_network.zoiko_vpc.id
  project       = var.project_id
}

# -----------------------------------------------------------------------
# Redis (Memorystore) — dev: basic tier, 1 GB
# -----------------------------------------------------------------------

resource "google_redis_instance" "zoiko_dev" {
  name           = "zoiko-dev-redis"
  memory_size_gb = 1
  tier           = "BASIC" # dev; prod = STANDARD_HA
  region         = var.region
  project        = var.project_id

  authorized_network = google_compute_network.zoiko_vpc.id

  redis_version = "REDIS_7_0"

  depends_on = [google_project_service.apis]
}

# -----------------------------------------------------------------------
# Artifact Registry — Docker images for all services
# -----------------------------------------------------------------------

resource "google_artifact_registry_repository" "zoiko_dev" {
  repository_id = "zoiko-services"
  location      = var.region
  format        = "DOCKER"
  project       = var.project_id

  depends_on = [google_project_service.apis]
}

# -----------------------------------------------------------------------
# Outputs consumed by CI and service deployments
# -----------------------------------------------------------------------

output "db_connection_name" {
  value = google_sql_database_instance.zoiko_dev.connection_name
}

output "redis_host" {
  value = google_redis_instance.zoiko_dev.host
}

output "kms_key_ring_id" {
  value = google_kms_key_ring.zoiko_dev.id
}

output "root_cmk_id" {
  value = google_kms_crypto_key.root_cmk.id
}

output "artifact_registry_url" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/zoiko-services"
}
