from dataclasses import dataclass
import uuid
from datetime import datetime


@dataclass
class TokenResult:
    token_id:       uuid.UUID
    tenant_id:      str
    decision_id:    str
    case_id:        str
    scope:          str
    status:         str         # ACTIVE
    token_hash:     str         # hex
    tenant_binding: str         # hex SHA-256(tenant_id || decision_id)
    expires_at:     datetime
    issued_at:      datetime
