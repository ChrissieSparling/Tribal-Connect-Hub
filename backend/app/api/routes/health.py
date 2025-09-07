from fastapi import APIRouter

# router = APIRouter(prefix="/routes", tags=["health"])
router = APIRouter(tags=["health"])

@router.get("/health")
def health():
    return {"status": "ok"}
