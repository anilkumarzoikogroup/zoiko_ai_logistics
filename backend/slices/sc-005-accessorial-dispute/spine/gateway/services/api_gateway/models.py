from pydantic import BaseModel
from typing import List, Optional

class ChargeLineInput(BaseModel):
    charge_type:    str           # DETENTION / DEMURRAGE / LIFTGATE / RESIDENTIAL / FUEL_SURCHARGE / OTHER
    billed_amount:  float
    contracted_cap: float
    tariff_id:      Optional[str] = None
    tariff_version: Optional[str] = None

class SubmitAccessorialRequest(BaseModel):
    carrier_id:         str
    invoice_reference:  str
    invoice_date:       str
    charge_lines:       List[ChargeLineInput]
    currency:           str = "INR"

class UIProposalRequest(BaseModel):
    finding_id: str
    amount:     float
    currency:   str = "INR"
    actor_sub:  str

class UIDecideRequest(BaseModel):
    task_id:    str
    decision:   str   # APPROVE | REJECT
    note:       Optional[str] = ""
    actor_sub:  str
