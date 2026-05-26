# Alert: high error rate on Phase 2 API
resource "google_monitoring_alert_policy" "p2_error_rate" {
  project      = var.project_id
  display_name = "Zoiko ${var.env}: Phase2 5xx error rate"
  combiner     = "OR"

  conditions {
    display_name = "Phase2 5xx > 1%"
    condition_threshold {
      filter          = "resource.type=\"cloud_run_revision\" AND metric.type=\"run.googleapis.com/request_count\" AND metric.labels.response_code_class=\"5xx\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0.01
      duration        = "60s"
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_RATE"
      }
    }
  }

  notification_channels = var.notification_channels
  severity              = var.env == "production" ? "CRITICAL" : "WARNING"
}

# Alert: token consumption latency
resource "google_monitoring_alert_policy" "execution_latency" {
  project      = var.project_id
  display_name = "Zoiko ${var.env}: Execution latency p99 > 5s"
  combiner     = "OR"

  conditions {
    display_name = "Execution p99 > 5s"
    condition_threshold {
      filter          = "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"zoiko-phase4-${var.env}\""
      comparison      = "COMPARISON_GT"
      threshold_value = 5000
      duration        = "300s"
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_PERCENTILE_99"
      }
    }
  }

  notification_channels = var.notification_channels
  severity              = "WARNING"
}
