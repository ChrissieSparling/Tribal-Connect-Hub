from __future__ import annotations

# stdlib
import os
from datetime import date, datetime
from enum import Enum
from io import BytesIO
from pathlib import Path as FilePath
# typing
from typing import Optional, List, Dict, Literal, Generator

# third-party
import qrcode
from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Path as PathParam,
    Query,
    Request,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    func,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    sessionmaker,
)

# -------- Paths & DB --------
BASE_DIR = FilePath(__file__).resolve().parent
DATABASE_URL = f"sqlite:///{(BASE_DIR / 'tribalconnect.db').as_posix()}"
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

    memberships: Mapped[List["Membership"]] = relationship("Membership", back_populates="tribe", cascade="all, delete-orphan")


# Unified User model (auth + app fields)
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Auth + identity
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True, nullable=False)
    password: Mapped[str] = mapped_column(String(255), nullable=False)

    # Optional profile
    first_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # App-specific
    tribe_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tribal_id_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    role: Mapped[str] = mapped_column(String(30), default="member", nullable=False)  # member|admin|enrollment
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    memberships: Mapped[List["Membership"]] = relationship("Membership", back_populates="user", cascade="all, delete-orphan")


# Additional names per person (maiden, clan, traditional, etc.)
class PersonName(Base):
    __tablename__ = "person_names"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    text: Mapped[str] = mapped_column(String(300))             # full name as written
    type: Mapped[str] = mapped_column(String(40), index=True)  # legal|maiden|family_lineage|clan|traditional|...
    language: Mapped[Optional[str]] = mapped_column(String(16))
    script: Mapped[Optional[str]] = mapped_column(String(32))

    given_by: Mapped[Optional[str]] = mapped_column(String(200))
    given_on: Mapped[Optional[date]] = mapped_column(Date)
    meaning: Mapped[Optional[str]] = mapped_column(Text)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    visibility: Mapped[str] = mapped_column(String(20), default="private", nullable=False)  # public|members_only|tribe_only|private
    source: Mapped[Optional[str]] = mapped_column(String(80))

    user: Mapped["User"] = relationship("User", backref="names")


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[RoleName] = mapped_column(SAEnum(RoleName))
    description: Mapped[Optional[str]] = mapped_column(String(300))

    assignments: Mapped[List["RoleAssignment"]] = relationship("RoleAssignment", back_populates="role", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("name", name="uq_role_name"),)


class Membership(Base):
    __tablename__ = "memberships"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    tribe_id: Mapped[int] = mapped_column(ForeignKey("tribes.id", ondelete="CASCADE"))
    enrollment_number: Mapped[Optional[str]] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(50), default="active")

    user: Mapped["User"] = relationship("User", back_populates="memberships")
    tribe: Mapped["Tribe"] = relationship("Tribe", back_populates="memberships")
    roles: Mapped[List["RoleAssignment"]] = relationship("RoleAssignment", back_populates="membership", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("user_id", "tribe_id", name="uq_user_tribe"),)


class RoleAssignment(Base):
    __tablename__ = "role_assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    membership_id: Mapped[int] = mapped_column(ForeignKey("memberships.id", ondelete="CASCADE"))
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"))

    membership: Mapped["Membership"] = relationship("Membership", back_populates="roles")
    role: Mapped["Role"] = relationship("Role", back_populates="assignments")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tribe_id: Mapped[int] = mapped_column(ForeignKey("tribes.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[Optional[str]] = mapped_column(String(2000))
    start_date: Mapped[date] = mapped_column(Date, index=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(200))

    tribe: Mapped["Tribe"] = relationship("Tribe", backref="events")


class EventDetails(Base):
    __tablename__ = "event_details"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), unique=True)
    external_url: Mapped[Optional[str]] = mapped_column(String(500))
    parking_info: Mapped[Optional[str]] = mapped_column(String(2000))
    shuttle_info: Mapped[Optional[str]] = mapped_column(String(2000))
    carpool_url: Mapped[Optional[str]] = mapped_column(String(500))
    camping_checklist: Mapped[dict] = mapped_column(JSON, default=dict)
    lat: Mapped[Optional[float]] = mapped_column(Float)
    lon: Mapped[Optional[float]] = mapped_column(Float)
    privacy: Mapped[str] = mapped_column(String(20), default="public")  # "public" or "tribal_only"

    event: Mapped["Event"] = relationship("Event", backref="details", uselist=False)


class EventMedia(Base):
    __tablename__ = "event_media"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    uploader_name: Mapped[Optional[str]] = mapped_column(String(200))
    visibility: Mapped[str] = mapped_column(String(20), default="public")  # "public" | "tribal_only"
    file_path: Mapped[str] = mapped_column(String(500))  # relative path under /static/uploads
    mime_type: Mapped[Optional[str]] = mapped_column(String(120))
    caption: Mapped[Optional[str]] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    event: Mapped["Event"] = relationship("Event", backref="media")

# ---------- Businesses ----------
class BusinessCategory(Base):
    __tablename__ = "business_categories"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(120))

class Business(Base):
    __tablename__ = "businesses"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tribe_id: Mapped[int] = mapped_column(ForeignKey("tribes.id", ondelete="CASCADE"), index=True)

    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[Optional[str]] = mapped_column(String(2000))
    website_url: Mapped[Optional[str]] = mapped_column(String(300))
    storefront_url: Mapped[Optional[str]] = mapped_column(String(300))  # direct “buy”/shop link
    email: Mapped[Optional[str]] = mapped_column(String(200))
    phone: Mapped[Optional[str]] = mapped_column(String(50))
    logo_url: Mapped[Optional[str]] = mapped_column(String(400))

    category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("business_categories.id", ondelete="SET NULL"), nullable=True)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    visibility: Mapped[str] = mapped_column(String(20), default="public")  # public | tribe_only

    tribe: Mapped["Tribe"] = relationship("Tribe", backref="businesses")
    category: Mapped[Optional["BusinessCategory"]] = relationship("BusinessCategory")

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

# --------------------------
# Business Schemas
# --------------------------
class BusinessOut(BaseModel):
    id: int
    tribe_id: int
    name: str
    description: Optional[str]
    website_url: Optional[str]
    storefront_url: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    logo_url: Optional[str]
    category_id: Optional[int]
    is_featured: bool
    is_active: bool
    visibility: str
    class Config:
        from_attributes = True

class BusinessIn(BaseModel):
    name: str
    description: Optional[str] = None
    website_url: Optional[str] = None
    storefront_url: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    logo_url: Optional[str] = None
    category_id: Optional[int] = None
    is_featured: bool = False
    is_active: bool = True
    visibility: str = "public"

class BusinessPatch(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    website_url: Optional[str] = None
    storefront_url: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    logo_url: Optional[str] = None
    category_id: Optional[int] = None
    is_featured: Optional[bool] = None
    is_active: Optional[bool] = None
    visibility: Optional[str] = None
    class Config:
        extra = "forbid"

class BusinessOut(BaseModel):
    id: int
    tribe_id: int
    name: str
    description: Optional[str]
    website_url: Optional[str]
    storefront_url: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    logo_url: Optional[str]
    category_id: Optional[int]
    is_featured: bool
    is_active: bool
    visibility: str
    class Config:
        from_attributes = True

# ---------- Businesses (Pydantic) ----------
class BusinessCategoryOut(BaseModel):
    id: int
    slug: str
    label: str
    class Config:
        from_attributes = True

class BusinessOut(BaseModel):
    id: int
    tribe_id: int
    name: str
    description: Optional[str]
    website_url: Optional[str]
    storefront_url: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    logo_url: Optional[str]
    is_featured: bool
    is_active: bool
    visibility: str
    category: Optional[BusinessCategoryOut]
    class Config:
        from_attributes = True

class BusinessCreate(BaseModel):
    name: str
    description: Optional[str] = None
    website_url: Optional[str] = None
    storefront_url: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    logo_url: Optional[str] = None
    category_id: Optional[int] = None
    is_featured: bool = False
    is_active: bool = True
    visibility: str = "public"  # public | tribe_only

class BusinessUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    website_url: Optional[str] = None
    storefront_url: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    logo_url: Optional[str] = None
    category_id: Optional[int] = None
    is_featured: Optional[bool] = None
    is_active: Optional[bool] = None
    visibility: Optional[str] = None
    class Config:
        extra = "forbid"
# ==========================
# Pydantic schemas (Names)
# ==========================
class PersonNameIn(BaseModel):
    text: str
    type: str  # legal | maiden | family_lineage | clan | traditional | ceremonial | preferred | nickname | alias
    language: Optional[str] = None
    script: Optional[str] = None
    given_by: Optional[str] = None
    given_on: Optional[date] = None
    meaning: Optional[str] = None
    notes: Optional[str] = None
    is_primary: bool = False
    visibility: str = "private"  # public | members_only | tribe_only | private
    source: Optional[str] = "self-reported"


class PersonNamePatch(BaseModel):
    text: Optional[str] = None
    type: Optional[str] = None
    language: Optional[str] = None
    script: Optional[str] = None
    given_by: Optional[str] = None
    given_on: Optional[date] = None
    meaning: Optional[str] = None
    notes: Optional[str] = None
    is_primary: Optional[bool] = None
    visibility: Optional[str] = None
    source: Optional[str] = None

    class Config:
        extra = "forbid"


class PersonNameOut(BaseModel):
    id: int
    user_id: int
    text: str
    type: str
    language: Optional[str]
    script: Optional[str]
    given_by: Optional[str]
    given_on: Optional[date]
    meaning: Optional[str]
    notes: Optional[str]
    is_primary: bool
    visibility: str
    source: Optional[str]

    class Config:
        from_attributes = True


# ==========================
# FastAPI router
# ==========================
router = APIRouter(prefix="/core", tags=["core"])


# Dependency: DB session per request
def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Create tables and seed roles on startup
def register_events(app: FastAPI) -> None:
    @app.on_event("startup")
    def on_startup() -> None:
        # 1) Create all tables
        Base.metadata.create_all(engine)

        # 2) Ensure uploads dir exists
        os.makedirs(os.path.join(BASE_DIR, "static", "uploads"), exist_ok=True)

        # 3) Create indexes (after tables exist)
        with engine.begin() as conn:
            conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_events_start_date ON events (start_date)")
            conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_events_tribe_id ON events (tribe_id)")

            exists = conn.exec_driver_sql(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='person_names'"
            ).first()
            if exists:
                conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_person_names_user_id ON person_names (user_id)")
                conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_person_names_type ON person_names (type)")

        # 4) Seed roles if empty
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
    sort: str = Query("name_asc", description="name_asc | name_desc | established_asc | established_desc"),
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
        query = query.order_by((Tribe.established_year.is_(None)).asc(), Tribe.established_year.asc())
    elif sort == "established_desc":
        query = query.order_by((Tribe.established_year.is_(None)).asc(), Tribe.established_year.desc())
    else:  # name_asc (default)
        query = query.order_by(Tribe.name.asc())

    return query.offset(offset).limit(limit).all()


@router.get("/tribes/{tribe_id}", response_model=TribeOut)
def get_tribe(tribe_id: int = PathParam(..., gt=0), db: Session = Depends(get_db)):
    tribe = db.get(Tribe, tribe_id)
    if not tribe:
        raise HTTPException(status_code=404, detail="Tribe not found")
    return tribe


@router.patch("/tribes/{tribe_id}", response_model=TribeOut)
def update_tribe(
    tribe_id: int = PathParam(..., gt=0),
    payload: TribeUpdate = ...,
    db: Session = Depends(get_db),
):
    tribe = db.get(Tribe, tribe_id)
    if not tribe:
        raise HTTPException(status_code=404, detail="Tribe not found")

    data = payload.model_dump(exclude_unset=True)

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
def delete_tribe(tribe_id: int = PathParam(..., gt=0), db: Session = Depends(get_db)):
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
def list_events_for_tribe(tribe_id: int = PathParam(..., gt=0), db: Session = Depends(get_db)):
    tribe = db.get(Tribe, tribe_id)
    if not tribe:
        raise HTTPException(status_code=404, detail="Tribe not found")
    rows = db.query(Event).filter(Event.tribe_id == tribe_id).order_by(Event.start_date.desc()).all()
    return rows


@router.post("/tribes/{tribe_id}/events", response_model=EventOut)
def create_event_for_tribe(
    tribe_id: int = PathParam(..., gt=0),
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
def get_event(event_id: int = PathParam(..., gt=0), db: Session = Depends(get_db)):
    ev = db.get(Event, event_id)
    if not ev:
        raise HTTPException(status_code=404, detail="Event not found")
    return ev


@router.patch("/events/{event_id}", response_model=EventOut)
def update_event(
    event_id: int = PathParam(..., gt=0),
    payload: EventUpdate = ...,
    db: Session = Depends(get_db),
):
    ev = db.get(Event, event_id)
    if not ev:
        raise HTTPException(status_code=404, detail="Event not found")
    data = payload.model_dump(exclude_unset=True)
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
def delete_event(event_id: int = PathParam(..., gt=0), db: Session = Depends(get_db)):
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
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


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
    if visibility not in ("public", "tribal_only"):
        raise HTTPException(400, "visibility must be 'public' or 'tribal_only'")

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
    """Returns a PNG QR code that opens the public photo-share page for this event."""
    base = str(request.base_url).rstrip("/")
    url = f"{base}/events-html/{event_id}/share"

    img = qrcode.make(url)
    from io import BytesIO
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")

# --------------------------
# Routes: Business Categories (read-mostly)
# --------------------------
@router.get("/business_categories", response_model=List[BusinessCategoryOut] if "BusinessCategoryOut" in globals() else List[Dict])
def list_business_categories(db: Session = Depends(get_db)):
    rows = db.query(BusinessCategory).order_by(BusinessCategory.label.asc()).all()
    if "BusinessCategoryOut" in globals():
        return rows
    return [{"id": r.id, "slug": r.slug, "label": r.label} for r in rows]

@router.post("/business_categories", status_code=201)
def create_business_category(
    slug: str = Form(...),
    label: str = Form(...),
    db: Session = Depends(get_db),
):
    exists = db.query(BusinessCategory).filter(
        (BusinessCategory.slug == slug) | (BusinessCategory.label == label)
    ).first()
    if exists:
        raise HTTPException(400, "Category with that slug or label already exists")
    cat = BusinessCategory(slug=slug, label=label)
    db.add(cat); db.commit(); db.refresh(cat)
    return {"id": cat.id, "slug": cat.slug, "label": cat.label}

# --------------------------
# Routes: Businesses
# --------------------------
@router.get("/businesses", response_model=List[BusinessOut])
def list_businesses(
    tribe_id: Optional[int] = Query(None, gt=0),
    category_id: Optional[int] = Query(None, gt=0),
    q: Optional[str] = Query(None, description="Search name/description"),
    featured: Optional[bool] = Query(None),
    active: Optional[bool] = Query(True),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    qset = db.query(Business)
    if tribe_id:
        qset = qset.filter(Business.tribe_id == tribe_id)
    if category_id:
        qset = qset.filter(Business.category_id == category_id)
    if q:
        like = f"%{q.strip()}%"
        qset = qset.filter((Business.name.ilike(like)) | (Business.description.ilike(like)))
    if featured is not None:
        qset = qset.filter(Business.is_featured == featured)
    if active is not None:
        qset = qset.filter(Business.is_active == active)
    return qset.order_by(Business.is_featured.desc(), Business.name.asc()) \
               .offset(offset).limit(limit).all()

@router.post("/tribes/{tribe_id}/businesses", response_model=BusinessOut, status_code=201)
def create_business_for_tribe(
    tribe_id: int = PathParam(..., gt=0),
    payload: BusinessIn = ...,
    db: Session = Depends(get_db),
):
    tribe = db.get(Tribe, tribe_id)
    if not tribe:
        raise HTTPException(404, "Tribe not found")
    if payload.category_id:
        if not db.get(BusinessCategory, payload.category_id):
            raise HTTPException(400, "category_id not found")
    biz = Business(tribe_id=tribe_id, **payload.model_dump())
    db.add(biz); db.commit(); db.refresh(biz)
    return biz

@router.get("/businesses/{business_id}", response_model=BusinessOut)
def get_business(business_id: int = PathParam(..., gt=0), db: Session = Depends(get_db)):
    biz = db.get(Business, business_id)
    if not biz:
        raise HTTPException(404, "Business not found")
    return biz

@router.patch("/businesses/{business_id}", response_model=BusinessOut)
def update_business(
    business_id: int = PathParam(..., gt=0),
    payload: BusinessPatch = ...,
    db: Session = Depends(get_db),
):
    biz = db.get(Business, business_id)
    if not biz:
        raise HTTPException(404, "Business not found")
    data = payload.model_dump(exclude_unset=True)
    if "category_id" in data and data["category_id"]:
        if not db.get(BusinessCategory, data["category_id"]):
            raise HTTPException(400, "category_id not found")
    for k, v in data.items():
        setattr(biz, k, v)
    db.add(biz); db.commit(); db.refresh(biz)
    return biz

@router.delete("/businesses/{business_id}", status_code=204)
def delete_business(business_id: int = PathParam(..., gt=0), db: Session = Depends(get_db)):
    biz = db.get(Business, business_id)
    if not biz:
        raise HTTPException(404, "Business not found")
    db.delete(biz); db.commit()
    return None

@router.post("/businesses/{business_id}/feature", response_model=BusinessOut)
def feature_business(business_id: int, db: Session = Depends(get_db)):
    biz = db.get(Business, business_id)
    if not biz:
        raise HTTPException(404, "Business not found")
    biz.is_featured = True
    db.add(biz); db.commit(); db.refresh(biz)
    return biz

@router.post("/businesses/{business_id}/unfeature", response_model=BusinessOut)
def unfeature_business(business_id: int, db: Session = Depends(get_db)):
    biz = db.get(Business, business_id)
    if not biz:
        raise HTTPException(404, "Business not found")
    biz.is_featured = False
    db.add(biz); db.commit(); db.refresh(biz)
    return biz

# --------------------------
# Routes: Roles (read-only for now)
# --------------------------
@router.get("/roles", response_model=List[RoleOut])
def list_roles(db: Session = Depends(get_db)):
    return db.query(Role).order_by(Role.id.asc()).all()


# --------------------------
# Routes: Person Names
# --------------------------
@router.get("/users/{user_id}/names", response_model=List[PersonNameOut])
def list_person_names(
    user_id: int,
    include_private: bool = Query(False, description="Admins/matching user may set True"),
    db: Session = Depends(get_db),
):
    q = db.query(PersonName).filter(PersonName.user_id == user_id)
    if not include_private:
        q = q.filter(PersonName.visibility.in_(["public", "members_only", "tribe_only"]))
    rows = q.order_by(PersonName.is_primary.desc(), PersonName.id.asc()).all()
    return rows


@router.post("/users/{user_id}/names", response_model=PersonNameOut, status_code=201)
def create_person_name(
    user_id: int,
    payload: PersonNameIn,
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if payload.is_primary:
        db.query(PersonName).filter(PersonName.user_id == user_id, PersonName.is_primary == True).update(
            {"is_primary": False}
        )

    pn = PersonName(user_id=user_id, **payload.model_dump())
    db.add(pn)
    db.commit()
    db.refresh(pn)
    return pn


@router.patch("/users/{user_id}/names/{name_id}", response_model=PersonNameOut)
def update_person_name(
    user_id: int,
    name_id: int,
    payload: PersonNamePatch,
    db: Session = Depends(get_db),
):
    pn = db.get(PersonName, name_id)
    if not pn or pn.user_id != user_id:
        raise HTTPException(status_code=404, detail="Name not found")

    data = payload.model_dump(exclude_unset=True)

    if data.get("is_primary") is True:
        db.query(PersonName).filter(PersonName.user_id == user_id, PersonName.id != name_id).update(
            {"is_primary": False}
        )

    for k, v in data.items():
        setattr(pn, k, v)

    db.add(pn)
    db.commit()
    db.refresh(pn)
    return pn


@router.delete("/users/{user_id}/names/{name_id}", status_code=204)
def delete_person_name(
    user_id: int,
    name_id: int,
    db: Session = Depends(get_db),
):
    pn = db.get(PersonName, name_id)
    if not pn or pn.user_id != user_id:
        raise HTTPException(status_code=404, detail="Name not found")
    db.delete(pn)
    db.commit()
    return None

# ---------- DEV SEED: Washington tribes (federal + notable non-federal) ----------
@router.post("/dev/seed_wa_all", status_code=201)
def seed_washington_tribes(db: Session = Depends(get_db)):
    """
    One-time seeder for Washington tribes.
    - Adds 29 federally recognized + several notable non-federally recognized nations/communities.
    - Skips any tribe name that already exists.
    - Descriptions are concise and identity-forward; refine safely over time.
    """
    wa_tribes = [

        # ===== Federally recognized (29) =====
        {"name": "Confederated Tribes of the Chehalis Reservation", "short_name": "Chehalis",
         "recognition_type": RecognitionType.TREATY,
         "description": "People of the Chehalis River valleys; caretakers of river, salmon, and cedar lifeways."},

        {"name": "Confederated Tribes of the Colville Reservation", "short_name": "Colville",
         "recognition_type": RecognitionType.TREATY,
         "description": "Confederation of distinct bands from plateau and river homelands; salmon, roots, and trade trails."},

        {"name": "Cowlitz Indian Tribe", "short_name": "Cowlitz",
         "recognition_type": RecognitionType.RESTORED,
         "description": "Lower Columbia River people; renowned resilience as a landless tribe restored to recognition."},

        {"name": "Hoh Indian Tribe", "short_name": "Hoh",
         "recognition_type": RecognitionType.TREATY,
         "description": "Hoh River and Pacific shore people; cedar canoes, tide rhythms, and rainforest sustenance."},

        {"name": "Jamestown S'Klallam Tribe", "short_name": "Jamestown S’Klallam",
         "recognition_type": RecognitionType.RESTORED,
         "description": "Strong S’Klallam leadership and economic self-determination on the Strait of Juan de Fuca."},

        {"name": "Kalispel Tribe of Indians", "short_name": "Kalispel",
         "recognition_type": RecognitionType.TREATY,
         "description": "Pend Oreille River Salish people; riverine culture, language, and wildlife stewardship."},

        {"name": "Lower Elwha Klallam Tribe", "short_name": "Lower Elwha Klallam",
         "recognition_type": RecognitionType.TREATY,
         "description": "Elwha River people; leaders in dam removal and salmon restoration on their ancestral river."},

        {"name": "Lummi Nation", "short_name": "Lummi",
         "recognition_type": RecognitionType.TREATY,
         "description": "Xwlemi (Lummi) Coast Salish; reef-net fishing innovators and guardians of the Salish Sea."},

        {"name": "Makah Tribe", "short_name": "Makah",
         "recognition_type": RecognitionType.TREATY,
         "description": "Cape Flattery ocean people; whaling heritage, sea hunting, and coastal sciences."},

        {"name": "Muckleshoot Indian Tribe", "short_name": "Muckleshoot",
         "recognition_type": RecognitionType.TREATY,
         "description": "Enumclaw Plateau and river people; treaty fishing, hunting, and regional education leadership."},

        {"name": "Nisqually Indian Tribe", "short_name": "Nisqually",
         "recognition_type": RecognitionType.TREATY,
         "description": "Squalli-Absch; Nisqually River caretakers, Medicine Creek Treaty history, and salmon defense."},

        {"name": "Nooksack Indian Tribe", "short_name": "Nooksack",
         "recognition_type": RecognitionType.TREATY,
         "description": "Nuxwsa’7aq people of the Nooksack River and foothills; berry, salmon, and mountain pathways."},

        {"name": "Port Gamble S'Klallam Tribe", "short_name": "Port Gamble S’Klallam",
         "recognition_type": RecognitionType.TREATY,
         "description": "S’Klallam community of Port Gamble Bay; canoe culture and shellfish traditions."},

        {"name": "Puyallup Tribe of Indians", "short_name": "Puyallup",
         "recognition_type": RecognitionType.TREATY,
         "description": "S’Puyaləpabš; tideflat people and Boldt Decision fishing rights champions of the Puyallup River."},

        {"name": "Quileute Tribe", "short_name": "Quileute",
         "recognition_type": RecognitionType.TREATY,
         "description": "La Push ocean people; wolf origin stories, surf, and river-sea lifeways at Quillayute."},

        {"name": "Quinault Indian Nation", "short_name": "Quinault",
         "recognition_type": RecognitionType.TREATY,
         "description": "Rainforest nation of Lake Quinault and Pacific shore; towering cedar and salmon homelands."},

        {"name": "Samish Indian Nation", "short_name": "Samish",
         "recognition_type": RecognitionType.RESTORED,
         "description": "Coast Salish island and bay people; language revitalization and cultural resurgence."},

        {"name": "Sauk-Suiattle Indian Tribe", "short_name": "Sauk-Suiattle",
         "recognition_type": RecognitionType.TREATY,
         "description": "Mountain river nation of the Sauk and Suiattle; glacier waters, salmon, and cedar culture."},

        {"name": "Shoalwater Bay Indian Tribe", "short_name": "Shoalwater Bay",
         "recognition_type": RecognitionType.TREATY,
         "description": "Willapa Bay people; shellfish, tidal estuaries, and coastal storm resilience."},

        {"name": "Skokomish Indian Tribe", "short_name": "Skokomish",
         "recognition_type": RecognitionType.TREATY,
         "description": "Tuwaduq̓ of Hood Canal; canoe routes, elk, and shellfish along fjord waters."},

        {"name": "Snoqualmie Indian Tribe", "short_name": "Snoqualmie",
         "recognition_type": RecognitionType.RESTORED,
         "description": "People of the Moon; sacred Snoqualmie Falls carries prayers in the mist to Creator and ancestors."},

        {"name": "Spokane Tribe of Indians", "short_name": "Spokane",
         "recognition_type": RecognitionType.TREATY,
         "description": "Sp’q’n’i nation of the Plateau; river fisheries, trade networks, and root-gathering grounds."},

        {"name": "Stillaguamish Tribe of Indians", "short_name": "Stillaguamish",
         "recognition_type": RecognitionType.RESTORED,
         "description": "River people of the Stillaguamish; salmon habitat restoration and cedar craft."},

        {"name": "Suquamish Tribe", "short_name": "Suquamish",
         "recognition_type": RecognitionType.TREATY,
         "description": "dxʷsəqʷəb; home of Chief Seattle; canoe culture and Salish Sea stewardship."},

        {"name": "Swinomish Indian Tribal Community", "short_name": "Swinomish",
         "recognition_type": RecognitionType.TREATY,
         "description": "Channel and shoreline people; salmon habitat leadership on the Skagit delta."},

        {"name": "Tulalip Tribes", "short_name": "Tulalip",
         "recognition_type": RecognitionType.TREATY,
         "description": "Coast Salish community of Snohomish, Snoqualmie, and Skykomish lineages; trade, fisheries, and governance."},

        {"name": "Upper Skagit Indian Tribe", "short_name": "Upper Skagit",
         "recognition_type": RecognitionType.TREATY,
         "description": "Skagit River caretakers; mountain passes, salmon cycles, and cedar longhouses."},

        {"name": "Yakama Nation", "short_name": "Yakama",
         "recognition_type": RecognitionType.TREATY,
         "description": "River-and-plateau nation; salmon, roots, and horses across the Columbia and Yakima basins."},

        {"name": "Quinault Nation (Hoh/Quileute/Quinault/Queets area note)", "short_name": "Quinault/Queets",
         "recognition_type": RecognitionType.TREATY,
         "description": "Queets-Quinault coastal forests and river systems (note: distinct from Hoh and Quileute governments)."},


        # ===== Not federally recognized (not exhaustive) =====
        {"name": "Duwamish Tribe", "short_name": "Duwamish",
         "recognition_type": RecognitionType.NON_RECOGNIZED,
         "description": "Duwamish River people; descendants maintain community, culture, and services in Seattle."},

        {"name": "Chinook Indian Nation", "short_name": "Chinook",
         "recognition_type": RecognitionType.NON_RECOGNIZED,
         "description": "Lower Columbia River and Pacific shore people; master traders and canoe navigators."},

        {"name": "Steilacoom Tribe", "short_name": "Steilacoom",
         "recognition_type": RecognitionType.NON_RECOGNIZED,
         "description": "South Puget Sound heritage community; village, fort, and mission era crossroads."},

        {"name": "Snohomish Tribe of Indians", "short_name": "Snohomish (Heritage)",
         "recognition_type": RecognitionType.NON_RECOGNIZED,
         "description": "People of the Snohomish River; heritage community sustaining identity and history."},

        {"name": "Wanapum Band", "short_name": "Wanapum",
         "recognition_type": RecognitionType.NON_RECOGNIZED,
         "description": "Priest Rapids people of the mid-Columbia; caretakers of river places and petroglyphs."},
    ]

    created = 0
    for t in wa_tribes:
        if not db.query(Tribe).filter(Tribe.name == t["name"]).first():
            db.add(Tribe(
                name=t["name"],
                short_name=t.get("short_name"),
                recognition_type=t["recognition_type"],
                description=t.get("description"),
                website_url=t.get("website_url"),
            ))
            created += 1

    db.commit()
    return {"inserted": created, "message": "WA tribes seeded (existing names skipped)."}

# ---------- DEV SEED: Business Categories ----------
@router.post("/dev/seed_business_categories", status_code=201)
def seed_business_categories(db: Session = Depends(get_db)):
    categories = [
        {"slug": "arts_crafts", "label": "Arts & Crafts"},
        {"slug": "food", "label": "Food & Beverage"},
        {"slug": "lodging", "label": "Lodging"},
        {"slug": "tourism", "label": "Tourism & Experiences"},
        {"slug": "services", "label": "Professional Services"},
        {"slug": "education", "label": "Education & Training"},
        {"slug": "health", "label": "Health & Wellness"},
        {"slug": "agriculture", "label": "Agriculture & Foraging"},
        {"slug": "energy", "label": "Energy & Utilities"},
        {"slug": "construction", "label": "Construction & Trades"},
        {"slug": "casino_gaming", "label": "Gaming & Entertainment"},
        {"slug": "gov_enterprise", "label": "Government Enterprise"},
        {"slug": "ecom_shop", "label": "Online Shop"},
    ]
    created = 0
    for c in categories:
        if not db.query(BusinessCategory).filter(
            (BusinessCategory.slug == c["slug"]) | (BusinessCategory.label == c["label"])
        ).first():
            db.add(BusinessCategory(**c)); created += 1
    db.commit()
    return {"inserted": created}

# ---------- DEV SEED: Demo Businesses (WA) ----------
@router.post("/dev/seed_demo_businesses_wa", status_code=201)
def seed_demo_businesses_wa(db: Session = Depends(get_db)):
    # Lookup helpers
    cats = {c.slug: c.id for c in db.query(BusinessCategory).all()}
    tribes_by_short = {t.short_name or t.name: t.id for t in db.query(Tribe).all()}

    # Make sure categories exist
    required = ["casino_gaming", "tourism", "lodging", "arts_crafts", "services", "ecom_shop"]
    missing = [s for s in required if s not in cats]
    if missing:
        raise HTTPException(400, f"Missing categories: {', '.join(missing)}. Seed categories first.")

    demo = [
        # Snoqualmie
        {"tribe_short": "Snoqualmie", "name": "Snoqualmie Demo Tourism",
         "desc": "Example listing for a tribe-run tour/experience (demo).",
         "cat": "tourism", "site": "#", "shop": "#", "email": "hello@snoqualmie.demo", "phone": "000-000-0000",
         "logo": None, "featured": True},

        # Suquamish
        {"tribe_short": "Suquamish", "name": "Suquamish Demo Arts",
         "desc": "Example Native arts & crafts collective (demo).",
         "cat": "arts_crafts", "site": "#", "shop": "#", "email": "arts@suquamish.demo", "phone": None,
         "logo": None, "featured": False},

        # Tulalip
        {"tribe_short": "Tulalip", "name": "Tulalip Demo Services",
         "desc": "Example professional services (demo).",
         "cat": "services", "site": "#", "shop": None, "email": "contact@tulalip.demo", "phone": "000-000-0000",
         "logo": None, "featured": False},

        # Muckleshoot
        {"tribe_short": "Muckleshoot", "name": "Muckleshoot Demo Entertainment",
         "desc": "Example entertainment venue (demo).",
         "cat": "casino_gaming", "site": "#", "shop": None, "email": "info@muckleshoot.demo", "phone": None,
         "logo": None, "featured": True},

        # Quinault
        {"tribe_short": "Quinault", "name": "Quinault Demo Lodging",
         "desc": "Example lodging near the coast (demo).",
         "cat": "lodging", "site": "#", "shop": None, "email": "stay@quinault.demo", "phone": "000-000-0000",
         "logo": None, "featured": False},

        # Lummi
        {"tribe_short": "Lummi", "name": "Lummi Demo Online Shop",
         "desc": "Example e-commerce storefront (demo).",
         "cat": "ecom_shop", "site": "#", "shop": "#", "email": "shop@lummi.demo", "phone": None,
         "logo": None, "featured": False},
    ]

    created = 0
    for d in demo:
        tribe_id = tribes_by_short.get(d["tribe_short"])
        if not tribe_id:
            # skip quietly if tribe not in DB
            continue
        # idempotency: skip if a business with same name and tribe exists
        exists = db.query(Business).filter(
            Business.tribe_id == tribe_id, Business.name == d["name"]
        ).first()
        if exists:
            continue
        b = Business(
            tribe_id=tribe_id,
            name=d["name"],
            description=d["desc"],
            website_url=d["site"],
            storefront_url=d["shop"],
            email=d["email"],
            phone=d["phone"],
            logo_url=d["logo"],
            category_id=cats.get(d["cat"]),
            is_featured=d["featured"],
            is_active=True,
            visibility="public",
        )
        db.add(b); created += 1

    db.commit()
    return {"inserted": created, "note": "Demo entries only. Replace with real data later."}


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
