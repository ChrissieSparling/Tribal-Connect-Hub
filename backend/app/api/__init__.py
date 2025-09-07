from fastapi import APIRouter

from backend.tenants.router import router as tenants_router
from backend.approvals.router import router as approvals_router
from backend.audit.router import router as audit_router
from backend.native_registry.router import router as native_registry_router
from backend.tribal_core import router as core_router
from app.api.routes import health

api_router = APIRouter()

api_router.include_router(core_router)
api_router.include_router(tenants_router)
api_router.include_router(approvals_router)
api_router.include_router(audit_router)
api_router.include_router(native_registry_router)
api_router.include_router(health.router)