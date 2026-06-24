terraform {
  required_version = ">= 1.7"
  required_providers {
    google = { source = "hashicorp/google", version = "~> 5.0" }
  }
  backend "gcs" {
    bucket = "zoiko-logistics-staging-tfstate"
    prefix = "terraform/state"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

variable "project_id" { default = "zoiko-logistics-staging" }
variable "region"     { default = "us-central1" }

# Staging mirrors prod: HSM keys, full Kafka, HA Cloud SQL.
# Actual resources added in P1 after Q6 (GKE Standard vs Autopilot) is resolved.
# This file is a placeholder so `terraform init` succeeds.
