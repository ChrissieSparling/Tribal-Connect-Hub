from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Optional
from .router import router

router = APIRouter(prefix="/approvals", tags=["approvals"])

APPROVALS: Dict[str, dict] = {}

class ApprovalDraft(BaseModel):
    tenant_id: str
    actor_id: str
    action: str
    resource: str
    payload: dict

class ApprovalDecision(BaseModel):
    decision: str  # "approve" | "deny"
    reason: Optional[str] = None
    approver_id: str

@router.post("/draft")
def create_draft(d: ApprovalDraft):
    aid = f"appr_{len(APPROVALS)+1:06d}"
    APPROVALS[aid] = {"status":"pending", **d.dict()}
    return {"approval_id": aid, "status": "pending"}

@router.post("/{approval_id}/decision")
def decide(approval_id: str, dec: ApprovalDecision):
    appr = APPROVALS.get(approval_id)
    if not appr:
        raise HTTPException(status_code=404, detail="Not found")
    if dec.decision not in ("approve","deny"):
        raise HTTPException(status_code=400, detail="Invalid decision")
    appr["status"] = dec.decision
    appr["decision_reason"] = dec.reason
    appr["approver_id"] = dec.approver_id
    return {"approval_id": approval_id, "status": appr["status"]}
