"""
Ingestion Service Models — SC-003 Shipment Exception.

Domain: shipment SLA breach detection and penalty recovery.
Mirrors SC-002 carrier-claim models exactly; claim-specific fields are
replaced with shipment-exception fields.

ShipmentExceptionInput is the dedup-keyed inbound payload.
  - shipment_reference is the external dedup key (like claim_reference in SC-002).
  - committed_eta / actual_delivery are TIMESTAMPTZ-compatible ISO datetimes.
  - sla_breach_hours and penalty_amount are computed by the ingestion handler;
    they are NOT accepted from the caller (computed fields, not inputs).
  - event_stream is a list of tracking events:
      [{"event_type": str, "occurred_at": str (ISO), "location": str}, ...]
    Allowed event_type values: PICKUP, IN_TRANSIT, DELAYED, ARRIVED, DELIVERED, EXCEPTION

All other models (ChannelEnum, DeduplicationOutcome, RecordStatus,
IngestResult, ChannelMetadata*) are kept identical to SC-002 so that
shared handler code can be reused without modification.
"""
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


# ── Channel enumeration ────────────────────────────────────────────────────────

class ChannelEnum:
    REST_API_PUSH = "rest_api_push"
    REST_API_PULL = "rest_api_pull"
    WEBHOOK       = "webhook"
    EDI           = "edi"
    FILE_UPLOAD   = "file_upload"
    UI_ENTRY      = "ui_entry"


# ── Deduplication outcome ──────────────────────────────────────────────────────

class DeduplicationOutcome:
    FIRST_SEEN   = "FIRST_SEEN"
    DUPLICATE_OF = "DUPLICATE_OF"
    AMBIGUOUS    = "AMBIGUOUS"


# ── Source-record FSM states ───────────────────────────────────────────────────

class RecordStatus:
    RECEIVED           = "RECEIVED"
    PERSISTED          = "PERSISTED"
    DEDUPED            = "DEDUPED"
    ENCRYPTED          = "ENCRYPTED"
    SIGNED             = "SIGNED"
    PENDING_VALIDATION = "PENDING_VALIDATION"
    VALIDATING         = "VALIDATING"
    VALIDATED          = "VALIDATED"
    CANONICALIZING     = "CANONICALIZING"
    PROCESSED          = "PROCESSED"
    QUARANTINED        = "QUARANTINED"
    REJECTED           = "REJECTED"


# ── Valid tracking event types for event_stream ────────────────────────────────

class ShipmentEventType:
    PICKUP     = "PICKUP"
    IN_TRANSIT = "IN_TRANSIT"
    DELAYED    = "DELAYED"
    ARRIVED    = "ARRIVED"
    DELIVERED  = "DELIVERED"
    EXCEPTION  = "EXCEPTION"

    ALL = {PICKUP, IN_TRANSIT, DELAYED, ARRIVED, DELIVERED, EXCEPTION}


# ── Primary inbound payload ────────────────────────────────────────────────────

@dataclass
class ShipmentExceptionInput:
    """
    Caller-supplied fields for a shipment SLA exception.

    Fields that are computed by the ingestion handler and must NOT be
    supplied by the caller:
      - sla_breach_hours   — computed as max(0, (actual_delivery - committed_eta).total_seconds() / 3600)
      - penalty_amount     — computed as min(sla_breach_hours * penalty_rate_per_hour, penalty_cap)

    event_stream entries must conform to:
      {"event_type": ShipmentEventType.*, "occurred_at": "<ISO-8601>", "location": str}
    """
    # Identity / dedup key
    carrier_id:            str
    shipment_reference:    str        # external dedup key — maps to external_source_ref

    # SLA window
    committed_eta:         datetime   # promised delivery timestamp (TIMESTAMPTZ)
    actual_delivery:       datetime   # actual delivery timestamp  (TIMESTAMPTZ)

    # Route
    origin:                str   = ""
    destination:           str   = ""

    # Penalty parameters (from contract)
    penalty_rate_per_hour: float = 0.0
    penalty_cap:           float = 10000.0
    currency:              str   = "INR"

    # Supplementary
    description:           str   = ""
    event_stream:          list  = field(default_factory=list)
    # list of {"event_type": str, "occurred_at": str, "location": str}


# ── Ingestion result (returned to caller) ──────────────────────────────────────

@dataclass
class IngestResult:
    source_record_id:      UUID
    canonical_hash:        str   # hex string
    idempotency_key:       str
    tenant_id:             str
    deduplication_outcome: str   = DeduplicationOutcome.FIRST_SEEN
    correlation_id:        str   = None
    channel:               str   = ChannelEnum.REST_API_PUSH


# ── Channel metadata shapes ────────────────────────────────────────────────────
# Kept identical to SC-002 so shared adapter code requires no changes.

@dataclass
class ChannelMetadataRestPush:
    client_id:        str   = ""
    idempotency_key:  str   = ""
    content_digest:   str   = ""
    source_ip:        str   = ""
    user_agent:       str   = ""
    request_id:       str   = ""


@dataclass
class ChannelMetadataFileUpload:
    uploaded_by_user_id:   str   = ""
    upload_session_id:     str   = ""
    original_filename:     str   = ""
    declared_mime:         str   = ""
    detected_mime:         str   = ""
    malware_scan_id:       str   = ""
    malware_scan_outcome:  str   = "PENDING"
    declared_schema:       str   = ""
    declared_row_count:    int   = 0
    sheet_names:           list  = field(default_factory=list)


@dataclass
class ChannelMetadataWebhook:
    partner_id:         str   = ""
    webhook_id:         str   = ""
    webhook_timestamp:  str   = ""
    signature_alg:      str   = ""
    signature_key_id:   str   = ""
    signature_verified: bool  = False
    source_ip:          str   = ""
    sequence_number:    int   = 0
