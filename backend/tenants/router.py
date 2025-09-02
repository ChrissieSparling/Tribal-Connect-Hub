# backend/tenants/router.py
from fastapi import APIRouter

router = APIRouter(prefix="/tenants", tags=["tenants"])

@router.get("")
def list_tenants():
    return []  # TODO: wire to your DB/service
