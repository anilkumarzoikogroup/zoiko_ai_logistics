terraform {
  required_version = ">= 1.7"
  required_providers {
    google = { source = "hashicorp/google", version = "~> 5.0" }
  }
  backend "gcs" {
    bucket = "zoiko-logistics-prod-tfstate"
    prefix = "terraform/state"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

variable "project_id" { default = "zoiko-logistics-prod" }
variable "region"     { default = "us-central1" }

# Prod: HSM keys, HA Cloud SQL (REGIONAL), STANDARD_HA Redis, WORM bucket.
# WORM bucket must be provisioned manually (is_locked=true is irreversible).
# Do NOT apply this without Security + Compliance sign-off.
