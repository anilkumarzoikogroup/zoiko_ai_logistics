locals {
  services = {
    phase2       = { image = var.image_phase2,    port = 8000, name = "zoiko-phase2-${var.env}" }
    phase3       = { image = var.image_phase3,    port = 8002, name = "zoiko-phase3-${var.env}" }
    phase4       = { image = var.image_phase4,    port = 8001, name = "zoiko-phase4-${var.env}" }
    connector    = { image = var.image_connector, port = 8010, name = "zoiko-connector-${var.env}" }
    stub         = { image = var.image_stub,      port = 8013, name = "zoiko-stub-${var.env}" }
  }
}

resource "google_cloud_run_v2_service" "phase2" {
  project  = var.project_id
  name     = local.services.phase2.name
  location = var.region

  template {
    containers {
      image = var.image_phase2
      ports { container_port = 8000 }
      env { name = "DB_URL";          value_source { secret_key_ref { secret = var.db_secret_name; version = "latest" } } }
      env { name = "ZOIKO_DEV_MODE";  value = "false" }
      env { name = "KMS_KEY_NAME";    value = var.kms_key_name }
      env { name = "ZOIKO_RATE_LIMIT_ENABLED"; value = "true" }
    }
    vpc_access {
      connector = google_vpc_access_connector.connector.id
      egress    = "PRIVATE_RANGES_ONLY"
    }
    service_account = google_service_account.zoiko_run.email
  }
}

resource "google_cloud_run_v2_service" "phase4" {
  project  = var.project_id
  name     = local.services.phase4.name
  location = var.region

  template {
    containers {
      image = var.image_phase4
      ports { container_port = 8001 }
      env { name = "DB_URL"; value_source { secret_key_ref { secret = var.db_secret_name; version = "latest" } } }
    }
    vpc_access {
      connector = google_vpc_access_connector.connector.id
      egress    = "PRIVATE_RANGES_ONLY"
    }
    service_account = google_service_account.zoiko_run.email
  }
}

resource "google_cloud_run_v2_service" "connector_hub" {
  project  = var.project_id
  name     = local.services.connector.name
  location = var.region

  template {
    containers {
      image = var.image_connector
      ports { container_port = 8010 }
      env { name = "DB_URL"; value_source { secret_key_ref { secret = var.db_secret_name; version = "latest" } } }
    }
    service_account = google_service_account.zoiko_run.email
  }
}

resource "google_cloud_run_v2_service" "stub_service" {
  project  = var.project_id
  name     = local.services.stub.name
  location = var.region

  template {
    containers {
      image = var.image_stub
      ports { container_port = 8013 }
    }
    service_account = google_service_account.zoiko_run.email
  }
}

resource "google_service_account" "zoiko_run" {
  project      = var.project_id
  account_id   = "zoiko-run-${var.env}"
  display_name = "Zoiko Cloud Run SA (${var.env})"
}

resource "google_vpc_access_connector" "connector" {
  project       = var.project_id
  name          = "zoiko-${var.env}-vpc"
  region        = var.region
  ip_cidr_range = "10.8.0.0/28"
  network       = "zoiko-${var.env}"
}
