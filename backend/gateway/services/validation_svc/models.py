from dataclasses import dataclass, field
from uuid import UUID


@dataclass
class RateViolation:
    rule: str
    carrier_id: str
    rate_type: str
    expected: float
    actual: float
    delta: float


@dataclass
class ValidationResult:
    validation_id: UUID
    source_record_id: UUID
    tenant_id: str
    status: str                              # PASS | FAIL | WARN
    rule_violations: list[RateViolation] = field(default_factory=list)
    overcharge_amount: float = 0.0
    currency: str = "USD"
