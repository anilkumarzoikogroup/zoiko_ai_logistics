output "phase2_url"        { value = google_cloud_run_v2_service.phase2.uri }
output "phase4_url"        { value = google_cloud_run_v2_service.phase4.uri }
output "connector_hub_url" { value = google_cloud_run_v2_service.connector_hub.uri }
output "stub_service_url"  { value = google_cloud_run_v2_service.stub_service.uri }
