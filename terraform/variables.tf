variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "asia-south1"   # Mumbai — low latency for India freight ops
}

variable "env" {
  description = "Environment: dev | staging | production"
  type        = string
  validation {
    condition     = contains(["dev", "staging", "production"], var.env)
    error_message = "env must be dev, staging, or production"
  }
}

variable "db_tier" {
  description = "Cloud SQL machine type"
  type        = string
  default     = "db-g1-small"
}

variable "redis_tier" {
  description = "Memorystore tier: BASIC | STANDARD_HA"
  type        = string
  default     = "BASIC"
}

variable "image_phase2" {
  description = "Docker image for Phase 2 API gateway"
  type        = string
}

variable "image_phase3" {
  description = "Docker image for Phase 3 governance gateway"
  type        = string
}

variable "image_phase4" {
  description = "Docker image for Phase 4 execution gateway"
  type        = string
}

variable "image_connector_hub" {
  description = "Docker image for connector-hub (port 8010)"
  type        = string
}

variable "image_stub_service" {
  description = "Docker image for stub-service (port 8013)"
  type        = string
}
