from fastapi import APIRouter

from .appy import Base, engine, SessionLocal, seed_taxonomy

router = APIRouter(prefix="/native-registry", tags=["native_registry"])


@router.on_event("startup")
def init_schema():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_taxonomy(db)

