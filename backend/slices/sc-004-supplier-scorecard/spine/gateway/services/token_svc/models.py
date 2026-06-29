from dataclasses import dataclass
import uuid
from datetime import datetime


@dataclass
class TokenResult:
    token_id:            uuid.UUID
    tenant_id:           str
    decision_id:         str
    case_id:             str
    scope:               str
    status:              str
    token_hash:          str
    tenant_binding:      str
    expires_at:          datetime
    issued_at:           datetime
    approval_chain_hash: str = ""
    policy_version:      str = "v1.0.0"
