from dataclasses import dataclass, field
from uuid import UUID


class ChannelEnum:
    REST_API_PUSH = "rest_api_push"
    REST_API_PULL = "rest_api_pull"
    WEBHOOK       = "webhook"
    EDI           = "edi"
    FILE_UPLOAD   = "file_upload"
    UI_ENTRY      = "ui_entry"


class DeduplicationOutcome:
    FIRST_SEEN   = "FIRST_SEEN"
    DUPLICATE_OF = "DUPLICATE_OF"
    AMBIGUOUS    = "AMBIGUOUS"


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


@dataclass
class InvoiceInput:
    carrier_id:         str
    invoice_number:     str
    total_amount:       float
    currency:           str
    route_origin:       str
    route_destination:  str
    weight_lbs:         float = 0.0
    line_items:         dict  = field(default_factory=dict)
    invoice_date:       str   = ""
    transport_mode:     str   = ""
    equipment_type:     str   = ""
    charge_lines:       list  = field(default_factory=list)
    shipper_reference:  str   = ""


@dataclass
class IngestResult:
    source_record_id:      UUID
    canonical_hash:        str   # hex string
    idempotency_key:       str
    tenant_id:             str
    deduplication_outcome: str   = DeduplicationOutcome.FIRST_SEEN
    correlation_id:        str   = None
    channel:               str   = ChannelEnum.REST_API_PUSH


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
