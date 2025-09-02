from fastapi import APIRouter

router = APIRouter(prefix="/native-registry", tags=["native_registry"])

@router.get("")
def list_native_registry_items():
    return {"items": []}
