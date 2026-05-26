terraform {
  required_version = ">= 1.6.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.5"
    }
  }

  backend "gcs" {
    bucket = "zoiko-terraform-state"
    prefix = "terraform/state"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}

# ── VPC ───────────────────────────────────────────────────────────────────────
module "vpc" {
  source     = "./modules/vpc"
  project_id = var.project_id
  region     = var.region
  env        = var.env
}

# ── Cloud SQL (PostgreSQL) ────────────────────────────────────────────────────
module "cloud_sql" {
  source            = "./modules/cloud-sql"
  project_id        = var.project_id
  region            = var.region
  env               = var.env
  network_self_link = module.vpc.network_self_link
  db_name           = "zoiko"
  db_tier           = var.db_tier
}

# ── KMS ───────────────────────────────────────────────────────────────────────
module "kms" {
  source     = "./modules/kms"
  project_id = var.project_id
  region     = var.region
  env        = var.env
  keyring    = "zoiko-${var.env}"
}

# ── Redis (Memorystore) ───────────────────────────────────────────────────────
module "redis" {
  source            = "./modules/redis"
  project_id        = var.project_id
  region            = var.region
  env               = var.env
  network_self_link = module.vpc.network_self_link
  tier              = var.redis_tier
}

# ── Cloud Storage (WORM bucket) ───────────────────────────────────────────────
module "storage" {
  source     = "./modules/storage"
  project_id = var.project_id
  region     = var.region
  env        = var.env
}

# ── Secret Manager ────────────────────────────────────────────────────────────
module "secret_manager" {
  source     = "./modules/secret-manager"
  project_id = var.project_id
  env        = var.env
}

# ── IAM ───────────────────────────────────────────────────────────────────────
module "iam" {
  source     = "./modules/iam"
  project_id = var.project_id
  env        = var.env
}

# ── Cloud Run (Phase 2 API gateway) ──────────────────────────────────────────
module "cloud_run" {
  source            = "./modules/cloud-run"
  project_id        = var.project_id
  region            = var.region
  env               = var.env
  image_phase2      = var.image_phase2
  image_phase3      = var.image_phase3
  image_phase4      = var.image_phase4
  image_connector   = var.image_connector_hub
  image_stub        = var.image_stub_service
  db_connection     = module.cloud_sql.connection_name
  redis_host        = module.redis.host
  kms_key_name      = module.kms.signing_key_name
  db_secret_name    = module.secret_manager.db_password_secret
}

# ── Monitoring ────────────────────────────────────────────────────────────────
module "monitoring" {
  source     = "./modules/monitoring"
  project_id = var.project_id
  env        = var.env
}
