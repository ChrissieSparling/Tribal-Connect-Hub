from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict

# Create the router object for tenants
router = APIRouter(prefix="/tenants", tags=["tenants"])

# In-memory tenant store (we’ll swap this out for a DB later)
TENANTS: Dict[str, dict] = {}

class TenantCreate(BaseModel):
    tenant_id: str
    name: str
    policies: dict = {}

@router.post("")
def create_tenant(t: TenantCreate):
    """
    Create a new tenant (tribe).
    Example POST /tenants
    {
      "tenant_id": "sno",
      "name": "Snoqualmie",
      "policies": {"sharing": {"businessDirectory": "local"}}
    }
    """
    if t.tenant_id in TENANTS:
        raise HTTPException(status_code=409, detail="Tenant already exists")
    TENANTS[t.tenant_id] = t.dict()
    return {"created": t.tenant_id, "data": TENANTS[t.tenant_id]}

@router.get("")
def list_tenants():
    """
    List all tenants currently registered in the system.
    """
    return {"tenants": TENANTS}
