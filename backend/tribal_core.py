"""
Starter backend for TribalConnect Core focusing on:
- Tribal Profiles (treaty/IRA/non‑recognized)
- Multi-tribe RBAC scaffolding (roles per tribe)
- Seed data + simple CRUD for tribes and roles

Drop this file alongside your existing FastAPI app, or merge pieces into main.py.

Requirements (install):
pip install fastapi "uvicorn[standard]" sqlalchemy pydantic

Optional (for later auth):
pip install python-jose passlib[bcrypt]

To run for a quick test from this file alone:
uvicorn tribal_core:app --reload
"""
from __future__ import annotations

from enum import Enum
from typing import List, Optional, Dict
from fastapi import Query
from fastapi import Request
from fastapi import Depends, FastAPI, HTTPException, Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi import APIRouter
from pydantic import BaseModel, Field
from datetime import date
from fastapi import UploadFile, File, Form
from sqlalchemy import DateTime, Float
from datetime import datetime
import qrcode
from fastapi.responses import StreamingResponse
from io import BytesIO
from sqlalchemy import Date
from sqlalchemy import func
from sqlalchemy import (
    JSON,
    Boolean,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker, Session

# ==========================
# Database setup
# ==========================
DATABASE_URL = "sqlite:///./tribalconnect.db"  # swap to Postgres later
engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

class Base(DeclarativeBase):
    pass

# ==========================
# Enums & constants
# ==========================
class RecognitionType(str, Enum):
    TREATY = "treaty"
    IRA = "ira"
    STATE_RECOGNIZED = "state_recognized"
    NON_RECOGNIZED = "non_recognized"
    RESTORED = "restored"

class RoleName(str, Enum):
    SUPER_ADMIN = "super_admin"       # global
    COUNCIL = "council"
    DEPT_ADMIN = "department_admin"
    STAFF = "staff"
    MEMBER = "member"
    GUEST = "guest"

# ==========================
# SQLAlchemy models
# ==========================
class Tribe(Base):
    __tablename__ = "tribes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    short_name: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    recognition_type: Mapped[RecognitionType] = mapped_column(SAEnum(RecognitionType), default=RecognitionType.TREATY)
    description: Mapped[Optional[str]] = mapped_column(String(2000))
    established_year: Mapped[Optional[int]] = mapped_column(Integer)
    original_territory_note: Mapped[Optional[str]] = mapped_column(String(2000))
    website_url: Mapped[Optional[str]] = mapped_column(String(300))
    emblem_url: Mapped[Optional[str]] = mapped_column(String(300))
    settings: Mapped[dict] = mapped_column(JSON, default=dict)

    memberships: Mapped[List[Membership]] = relationship("Membership", back_populates="tribe", cascade="all, delete-orphan")

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(100))
    last_name: Mapped[Optional[str]] = mapped_column(String(100))
    # NOTE: add password hash fields later when wiring real auth
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    memberships: Mapped[List[Membership]] = relationship("Membership", back_populates="user", cascade="all, delete-orphan")

class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[RoleName] = mapped_column(SAEnum(RoleName))
    description: Mapped[Optional[str]] = mapped_column(String(300))

    assignments: Mapped[List[RoleAssignment]] = relationship("RoleAssignment", back_populates="role", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("name", name="uq_role_name"),)

class Membership(Base):
    __tablename__ = "memberships"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    tribe_id: Mapped[int] = mapped_column(ForeignKey("tribes.id", ondelete="CASCADE"))
    enrollment_number: Mapped[Optional[str]] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(50), default="active")

    user: Mapped[User] = relationship("User", back_populates="memberships")
    tribe: Mapped[Tribe] = relationship("Tribe", back_populates="memberships")
    roles: Mapped[List[RoleAssignment]] = relationship("RoleAssignment", back_populates="membership", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("user_id", "tribe_id", name="uq_user_tribe"),)

class RoleAssignment(Base):
    __tablename__ = "role_assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    membership_id: Mapped[int] = mapped_column(ForeignKey("memberships.id", ondelete="CASCADE"))
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"))

    membership: Mapped[Membership] = relationship("Membership", back_populates="roles")
    role: Mapped[Role] = relationship("Role", back_populates="assignments")

class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tribe_id: Mapped[int] = mapped_column(ForeignKey("tribes.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[Optional[str]] = mapped_column(String(2000))
    start_date: Mapped[date] = mapped_column(Date, index=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(200))

    # create a backref so you can access tribe.events
    tribe: Mapped["Tribe"] = relationship("Tribe", backref="events")

class EventDetails(Base):
    __tablename__ = "event_details"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), unique=True)
    external_url: Mapped[Optional[str]] = mapped_column(String(500))
    parking_info: Mapped[Optional[str]] = mapped_column(String(2000))
    shuttle_info: Mapped[Optional[str]] = mapped_column(String(2000))
    carpool_url: Mapped[Optional[str]] = mapped_column(String(500))
    camping_checklist: Mapped[dict] = mapped_column(JSON, default=dict)  # {"items": ["Water", "Warm coat", ...]}
    lat: Mapped[Optional[float]] = mapped_column(Float)
    lon: Mapped[Optional[float]] = mapped_column(Float)
    privacy: Mapped[str] = mapped_column(String(20), default="public")  # "public" or "tribal_only"

    event: Mapped["Event"] = relationship("Event", backref="details", uselist=False)

class EventMedia(Base):
    __tablename__ = "event_media"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    # simple for now; wire to real users later
    uploader_name: Mapped[Optional[str]] = mapped_column(String(200))
    visibility: Mapped[str] = mapped_column(String(20), default="public")  # "public" | "tribal_only"
    file_path: Mapped[str] = mapped_column(String(500))  # relative path under /static/uploads
    mime_type: Mapped[Optional[str]] = mapped_column(String(120))
    caption: Mapped[Optional[str]] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    event: Mapped["Event"] = relationship("Event", backref="media")
# ==========================
# Pydantic schemas
# ==========================
class TribeCreate(BaseModel):
    name: str
    short_name: Optional[str] = None
    recognition_type: RecognitionType = RecognitionType.TREATY
    description: Optional[str] = None
    established_year: Optional[int] = None
    original_territory_note: Optional[str] = None
    website_url: Optional[str] = None
    emblem_url: Optional[str] = None
    settings: dict = Field(default_factory=dict)

class TribeOut(BaseModel):
    id: int
    name: str
    short_name: Optional[str]
    recognition_type: RecognitionType
    description: Optional[str]
    established_year: Optional[int]
    original_territory_note: Optional[str]
    website_url: Optional[str]
    emblem_url: Optional[str]
    settings: dict

    class Config:
        from_attributes = True

class RoleOut(BaseModel):
    id: int
    name: RoleName
    description: Optional[str]

    class Config:
        from_attributes = True


class TribeUpdate(BaseModel):
    name: Optional[str] = None
    short_name: Optional[str] = None
    recognition_type: Optional[RecognitionType] = None
    description: Optional[str] = None
    established_year: Optional[int] = None
    original_territory_note: Optional[str] = None
    website_url: Optional[str] = None
    emblem_url: Optional[str] = None
    settings: Optional[dict] = None

    class Config:
        extra = "forbid"

class EventCreate(BaseModel):
    title: str
    description: Optional[str] = None
    start_date: date
    end_date: Optional[date] = None
    location: Optional[str] = None

class EventUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    location: Optional[str] = None

    class Config:
        extra = "forbid"

class EventOut(BaseModel):
    id: int
    tribe_id: int
    title: str
    description: Optional[str]
    start_date: date
    end_date: Optional[date]
    location: Optional[str]

    class Config:
        from_attributes = True

class EventDetailsIn(BaseModel):
    external_url: Optional[str] = None
    parking_info: Optional[str] = None
    shuttle_info: Optional[str] = None
    carpool_url: Optional[str] = None
    camping_checklist: Optional[dict] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    privacy: Optional[str] = None  # "public" or "tribal_only"

class EventDetailsOut(EventDetailsIn):
    id: int
    event_id: int
    class Config:
        from_attributes = True

class EventMediaOut(BaseModel):
    id: int
    event_id: int
    uploader_name: Optional[str]
    visibility: str
    file_path: str
    mime_type: Optional[str]
    caption: Optional[str]
    created_at: datetime
    class Config:
        from_attributes = True

# ==========================
# FastAPI app
# ==========================
# app = FastAPI(title="TribalConnect Core")
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],  # tighten later
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )
router = APIRouter(prefix="/core", tags=["core"])

# Dependency to get DB session per request

def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Create tables and seed roles on startup
def register_events(app: FastAPI) -> None:
    @app.on_event("startup")
    def on_startup() -> None:
        Base.metadata.create_all(engine)
        os.makedirs(os.path.join(BASE_DIR if 'BASE_DIR' in globals() else '.', 'static', 'uploads'), exist_ok=True)
        with engine.begin() as conn:
            conn.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_events_start_date ON events (start_date)"
            )
            conn.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_events_tribe_id ON events (tribe_id)"
            )
        with SessionLocal() as db:
            if db.query(Role).count() == 0:
                for r in RoleName:
                    db.add(Role(name=r, description=f"Role: {r}"))
                db.commit()

# --------------------------
# Routes: Tribes
# --------------------------
@router.get("/health")
def health():
    return {"ok": True}

@router.post("/tribes", response_model=TribeOut)
def create_tribe(payload: TribeCreate, db: Session = Depends(get_db)):
    if db.query(Tribe).filter(Tribe.name == payload.name).first():
        raise HTTPException(status_code=400, detail="Tribe with that name already exists")
    tribe = Tribe(**payload.model_dump())
    db.add(tribe)
    db.commit()
    db.refresh(tribe)
    return tribe

@router.get("/tribes", response_model=List[TribeOut])
def list_tribes(
    q: Optional[str] = Query(None, description="Case-insensitive match on tribe name"),
    sort: str = Query(
        "name_asc",
        description="name_asc | name_desc | established_asc | established_desc"
    ),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(Tribe)

    if q:
        query = query.filter(Tribe.name.ilike(f"%{q.strip()}%"))

    if sort == "name_desc":
        query = query.order_by(Tribe.name.desc())
    elif sort == "established_asc":
        # Put rows with NULL established_year at the end (SQLite-safe)
        query = query.order_by((Tribe.established_year.is_(None)).asc(),
                                Tribe.established_year.asc())
    elif sort == "established_desc":
        query = query.order_by((Tribe.established_year.is_(None)).asc(),
                                Tribe.established_year.desc())
    else:  # name_asc (default)
        query = query.order_by(Tribe.name.asc())

    return query.offset(offset).limit(limit).all()

@router.get("/tribes/{tribe_id}", response_model=TribeOut)
def get_tribe(tribe_id: int = Path(..., gt=0), db: Session = Depends(get_db)):
    tribe = db.get(Tribe, tribe_id)
    if not tribe:
        raise HTTPException(status_code=404, detail="Tribe not found")
    return tribe

@router.patch("/tribes/{tribe_id}", response_model=TribeOut)
def update_tribe(
    tribe_id: int = Path(..., gt=0),
    payload: TribeUpdate = ...,
    db: Session = Depends(get_db),
):
    tribe = db.get(Tribe, tribe_id)
    if not tribe:
        raise HTTPException(status_code=404, detail="Tribe not found")

    data = payload.model_dump(exclude_unset=True)

    # If changing name, keep it unique
    if "name" in data and data["name"] != tribe.name:
        exists = db.query(Tribe).filter(Tribe.name == data["name"]).first()
        if exists:
            raise HTTPException(status_code=400, detail="Tribe with that name already exists")

    for k, v in data.items():
        setattr(tribe, k, v)

    db.add(tribe)
    db.commit()
    db.refresh(tribe)
    return tribe


@router.delete("/tribes/{tribe_id}", status_code=204)
def delete_tribe(tribe_id: int = Path(..., gt=0), db: Session = Depends(get_db)):
    tribe = db.get(Tribe, tribe_id)
    if not tribe:
        raise HTTPException(status_code=404, detail="Tribe not found")
    db.delete(tribe)
    db.commit()
    return None  # 204 No Content

# --------------------------
# Routes: Events
# --------------------------
@router.get("/tribes/{tribe_id}/events", response_model=List[EventOut])
def list_events_for_tribe(tribe_id: int = Path(..., gt=0), db: Session = Depends(get_db)):
    tribe = db.get(Tribe, tribe_id)
    if not tribe:
        raise HTTPException(status_code=404, detail="Tribe not found")
    rows = db.query(Event).filter(Event.tribe_id == tribe_id).order_by(Event.start_date.desc()).all()
    return rows

@router.post("/tribes/{tribe_id}/events", response_model=EventOut)
def create_event_for_tribe(
    tribe_id: int = Path(..., gt=0),
    payload: EventCreate = ...,
    db: Session = Depends(get_db),
):
    tribe = db.get(Tribe, tribe_id)
    if not tribe:
        raise HTTPException(status_code=404, detail="Tribe not found")
    if payload.end_date and payload.end_date < payload.start_date:
        raise HTTPException(status_code=400, detail="end_date cannot be before start_date")
    ev = Event(tribe_id=tribe_id, **payload.model_dump())
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev

@router.get("/events/{event_id}", response_model=EventOut)
def get_event(event_id: int = Path(..., gt=0), db: Session = Depends(get_db)):
    ev = db.get(Event, event_id)
    if not ev:
        raise HTTPException(status_code=404, detail="Event not found")
    return ev

@router.patch("/events/{event_id}", response_model=EventOut)
def update_event(
    event_id: int = Path(..., gt=0),
    payload: EventUpdate = ...,
    db: Session = Depends(get_db),
):
    ev = db.get(Event, event_id)
    if not ev:
        raise HTTPException(status_code=404, detail="Event not found")
    data = payload.model_dump(exclude_unset=True)
    # simple date sanity: if both provided, validate order
    sd = data.get("start_date", ev.start_date)
    ed = data.get("end_date", ev.end_date)
    if ed and sd and ed < sd:
        raise HTTPException(status_code=400, detail="end_date cannot be before start_date")
    for k, v in data.items():
        setattr(ev, k, v)
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev

@router.delete("/events/{event_id}", status_code=204)
def delete_event(event_id: int = Path(..., gt=0), db: Session = Depends(get_db)):
    ev = db.get(Event, event_id)
    if not ev:
        raise HTTPException(status_code=404, detail="Event not found")
    db.delete(ev)
    db.commit()
    return None

@router.get("/events", response_model=List[EventOut])
def list_events(
    start: Optional[date] = Query(None, description="YYYY-MM-DD"),
    end:   Optional[date] = Query(None, description="YYYY-MM-DD"),
    tribe_id: Optional[int] = Query(None, gt=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    q = db.query(Event)
    if tribe_id:
        q = q.filter(Event.tribe_id == tribe_id)
    if start:
        q = q.filter(Event.start_date >= start)
    if end:
        q = q.filter(Event.start_date <= end)
    rows = q.order_by(Event.start_date.asc()).limit(limit).all()
    return rows

@router.get("/tribes/event_counts", response_model=Dict[int, int])
def tribe_event_counts(
    upcoming_only: bool = Query(False, description="Count only events with start_date >= today"),
    db: Session = Depends(get_db),
):
    q = db.query(Event.tribe_id, func.count(Event.id))
    if upcoming_only:
        q = q.filter(Event.start_date >= date.today())
    rows = q.group_by(Event.tribe_id).all()
    return {tribe_id: count for tribe_id, count in rows}

# ----- Event Details (get/create/update) -----
@router.get("/events/{event_id}/details", response_model=EventDetailsOut)
def get_event_details(event_id: int, db: Session = Depends(get_db)):
    det = db.query(EventDetails).filter(EventDetails.event_id == event_id).first()
    if not det:
        raise HTTPException(404, "No details yet for this event")
    return det

@router.put("/events/{event_id}/details", response_model=EventDetailsOut)
def put_event_details(event_id: int, payload: EventDetailsIn, db: Session = Depends(get_db)):
    det = db.query(EventDetails).filter(EventDetails.event_id == event_id).first()
    if not det:
        det = EventDetails(event_id=event_id)
        db.add(det)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(det, k, v)
    db.commit(); db.refresh(det)
    return det

@router.patch("/events/{event_id}/details", response_model=EventDetailsOut)
def patch_event_details(event_id: int, payload: EventDetailsIn, db: Session = Depends(get_db)):
    det = db.query(EventDetails).filter(EventDetails.event_id == event_id).first()
    if not det:
        raise HTTPException(404, "No details yet for this event")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(det, k, v)
    db.commit(); db.refresh(det)
    return det

# ----- Event Media (upload/list) -----
UPLOAD_DIR = os.path.join(".", "static", "uploads")

@router.get("/events/{event_id}/media", response_model=List[EventMediaOut])
def list_event_media(event_id: int, include_private: bool = False, db: Session = Depends(get_db)):
    q = db.query(EventMedia).filter(EventMedia.event_id == event_id)
    if not include_private:
        q = q.filter(EventMedia.visibility == "public")
    return q.order_by(EventMedia.created_at.desc()).all()

@router.post("/events/{event_id}/media", response_model=EventMediaOut)
def upload_event_media(
    event_id: int,
    file: UploadFile = File(...),
    caption: str = Form(""),
    visibility: str = Form("public"),           # "public" or "tribal_only"
    uploader_name: str = Form(""),
    db: Session = Depends(get_db),
):
    # basic safety
    if visibility not in ("public", "tribal_only"):
        raise HTTPException(400, "visibility must be 'public' or 'tribal_only'")

    # save file
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    safe_name = f"event{event_id}_{int(datetime.utcnow().timestamp())}_{file.filename}"
    dest_path = os.path.join(UPLOAD_DIR, safe_name)
    with open(dest_path, "wb") as f:
        f.write(file.file.read())

    media = EventMedia(
        event_id=event_id,
        uploader_name=uploader_name or None,
        visibility=visibility,
        file_path=f"/static/uploads/{safe_name}",
        mime_type=file.content_type,
        caption=caption or None,
    )
    db.add(media); db.commit(); db.refresh(media)
    return media

# ----- Event Share QR (PNG) -----
@router.get("/events/{event_id}/share_qr.png")
def event_share_qr(event_id: int, request: Request):
    """
    Returns a PNG QR code that opens the public photo-share page for this event.
    """
    # Build an absolute URL so QR scanner apps work outside localhost context
    # e.g., http://127.0.0.1:8000/events-html/123/share
    base = str(request.base_url).rstrip("/")
    url = f"{base}/events-html/{event_id}/share"

    img = qrcode.make(url)
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")
# --------------------------
# Routes: Roles (read-only for now)
# --------------------------
@router.get("/roles", response_model=List[RoleOut])
def list_roles(db: Session = Depends(get_db)):
    return db.query(Role).order_by(Role.id.asc()).all()

# ==========================
# Permission scaffolding (RBAC)
# ==========================
"""
In the next step, we'll wire actual auth + per-tribe permission checks.
For now, the data model supports:
- Users with memberships in multiple tribes
- Role assignments per membership (so a user can be STAFF in Tribe A and COUNCIL in Tribe B)

When ready, add:
- /auth/register, /auth/login endpoints with JWT
- @requires_role(RoleName.COUNCIL, tribe_id) dependency
"""
