"""
Native Business Registry & TERO Hub
Schema (SQLAlchemy), seed data, and FastAPI routes
Stack: FastAPI + SQLAlchemy 2.0 + Pydantic v2 + Jinja2 (server-rendered; Bootstrap ready)

Notes:
- Uses dynamic categories/subcategories so you can expand without migrations.
- Adds gaming class taxonomy, compliance links, reviews, photos, and clothing fit data.
- Moderation-ready (review status, flagging) with simple roles.
- Replace `DB_URL` with your actual connection string.
"""

from __future__ import annotations
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, List

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import Request
from pydantic import BaseModel, Field
from sqlalchemy import (
    create_engine, ForeignKey, String, Integer, Text, DateTime, Enum as SAEnum,
    UniqueConstraint, Index, Boolean, Float, CheckConstraint
)
from sqlalchemy.orm import (
    DeclarativeBase, Mapped, mapped_column, relationship, Session, sessionmaker
)
import re
import os

# -----------------------------------------------------------------------------
# DB setup
# -----------------------------------------------------------------------------
DB_URL = "sqlite:///./native_registry.db"  # swap for Postgres: postgresql+psycopg://user:pass@host/db
engine = create_engine(DB_URL, echo=False, future=True)
SessionLocal = sessionmaker(engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


# -----------------------------------------------------------------------------
# Enums & Constants
# -----------------------------------------------------------------------------
class Role(str, Enum):
    admin = "admin"
    moderator = "moderator"
    member = "member"
    guest = "guest"


class ReviewStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class GamingClass(str, Enum):
    class_I = "Class I"
    class_II = "Class II"
    class_III = "Class III"


# -----------------------------------------------------------------------------
# Core Models
# -----------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    role: Mapped[Role] = mapped_column(SAEnum(Role), default=Role.member)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    reviews: Mapped[List[Review]] = relationship(back_populates="author")


class Tribe(Base):
    __tablename__ = "tribes"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    abbreviation: Mapped[Optional[str]] = mapped_column(String(32))


class Category(Base):
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    slug: Mapped[str] = mapped_column(String(140), unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text)

    subcategories: Mapped[List[SubCategory]] = relationship(back_populates="category", cascade="all, delete-orphan")


class SubCategory(Base):
    __tablename__ = "subcategories"
    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(140))
    slug: Mapped[str] = mapped_column(String(160))
    description: Mapped[Optional[str]] = mapped_column(Text)

    category: Mapped[Category] = relationship(back_populates="subcategories")
    __table_args__ = (
        UniqueConstraint("category_id", "slug", name="uq_subcategory_category_slug"),
        Index("ix_subcategory_category", "category_id"),
    )


class Business(Base):
    __tablename__ = "businesses"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    slug: Mapped[str] = mapped_column(String(300), unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    tribe_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tribes.id"))
    owner_type: Mapped[Optional[str]] = mapped_column(String(50))  # tribal_enterprise | tribal_member
    website: Mapped[Optional[str]] = mapped_column(String(500))
    email: Mapped[Optional[str]] = mapped_column(String(255))
    phone: Mapped[Optional[str]] = mapped_column(String(40))
    street: Mapped[Optional[str]] = mapped_column(String(255))
    city: Mapped[Optional[str]] = mapped_column(String(120))
    state: Mapped[Optional[str]] = mapped_column(String(64))
    postal_code: Mapped[Optional[str]] = mapped_column(String(20))
    country: Mapped[Optional[str]] = mapped_column(String(64))
    latitude: Mapped[Optional[float]] = mapped_column(Float)
    longitude: Mapped[Optional[float]] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    tribe: Mapped[Optional[Tribe]] = relationship()
    subcategories: Mapped[List[BusinessSubCategory]] = relationship(back_populates="business", cascade="all, delete-orphan")
    media: Mapped[List[MediaAsset]] = relationship(back_populates="business", cascade="all, delete-orphan")
    links: Mapped[List[LegalLink]] = relationship(back_populates="business", cascade="all, delete-orphan")
    compliance: Mapped[List[ComplianceRecord]] = relationship(back_populates="business", cascade="all, delete-orphan")
    reviews: Mapped[List[Review]] = relationship(back_populates="business", cascade="all, delete-orphan")
    size_feedback: Mapped[List[SizeFeedback]] = relationship(back_populates="business", cascade="all, delete-orphan")


class BusinessSubCategory(Base):
    __tablename__ = "business_subcategories"
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), primary_key=True)
    subcategory_id: Mapped[int] = mapped_column(ForeignKey("subcategories.id", ondelete="CASCADE"), primary_key=True)

    business: Mapped[Business] = relationship(back_populates="subcategories")
    subcategory: Mapped[SubCategory] = relationship()


class MediaAsset(Base):
    __tablename__ = "media_assets"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    url: Mapped[str] = mapped_column(String(800))  # local path or CDN
    caption: Mapped[Optional[str]] = mapped_column(String(255))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)

    business: Mapped[Business] = relationship(back_populates="media")


class LegalLink(Base):
    __tablename__ = "legal_links"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(200))  # e.g., "NIGC profile", "State compact"
    url: Mapped[str] = mapped_column(String(800))

    business: Mapped[Business] = relationship(back_populates="links")


class ComplianceRecord(Base):
    __tablename__ = "compliance_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(120))  # e.g., "gaming_class", "license_no", "compact_id"
    value: Mapped[str] = mapped_column(String(400))

    business: Mapped[Business] = relationship(back_populates="compliance")
    __table_args__ = (Index("ix_compliance_key", "key"),)


class Review(Base):
    __tablename__ = "reviews"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    rating: Mapped[int] = mapped_column(Integer)
    status: Mapped[ReviewStatus] = mapped_column(SAEnum(ReviewStatus), default=ReviewStatus.pending)
    flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    business: Mapped[Business] = relationship(back_populates="reviews")
    author: Mapped[Optional[User]] = relationship(back_populates="reviews")

    __table_args__ = (
        CheckConstraint("rating BETWEEN 1 AND 5", name="ck_review_rating_range"),
        Index("ix_review_status", "status"),
    )


class SizeFeedback(Base):
    __tablename__ = "size_feedback"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    product_name: Mapped[Optional[str]] = mapped_column(String(200))
    usual_size: Mapped[Optional[str]] = mapped_column(String(40))
    purchased_size: Mapped[Optional[str]] = mapped_column(String(40))
    fit_notes: Mapped[Optional[str]] = mapped_column(Text)
    fit_scale: Mapped[int] = mapped_column(Integer, default=0)  # -2 small, -1 slightly small, 0 true, +1 slightly large, +2 large
    culture_notes: Mapped[Optional[str]] = mapped_column(Text)  # cultural significance text
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    business: Mapped[Business] = relationship(back_populates="size_feedback")


# -----------------------------------------------------------------------------
# Pydantic DTOs
# -----------------------------------------------------------------------------
class ReviewCreate(BaseModel):
    title: str
    body: str
    rating: int = Field(ge=1, le=5)


class SizeFeedbackCreate(BaseModel):
    product_name: Optional[str] = None
    usual_size: Optional[str] = None
    purchased_size: Optional[str] = None
    fit_notes: Optional[str] = None
    fit_scale: int = Field(ge=-2, le=2)
    culture_notes: Optional[str] = None


class BusinessCreate(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None
    tribe_id: Optional[int] = None
    owner_type: Optional[str] = None
    website: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    street: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    subcategory_ids: List[int] = []


class BusinessOut(BaseModel):
    id: int
    name: str
    slug: str
    description: Optional[str]
    avg_rating: Optional[float] = None


# -----------------------------------------------------------------------------
# App & static [paths and] Templates
# -----------------------------------------------------------------------------
app = FastAPI(title="Native Business Registry & TERO Hub")

static_path = Path(__file__).resolve().parent.parent / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=static_path), name="static")
templates = Jinja2Templates(directory="templates")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# -----------------------------------------------------------------------------
# Utility: slugify
# -----------------------------------------------------------------------------

def slugify(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9\s-]", "", value).strip().lower()
    value = re.sub(r"[\s_-]+", "-", value)
    return value


# -----------------------------------------------------------------------------
# DB init
# -----------------------------------------------------------------------------


def register_events(app: FastAPI) -> None:
    """Attach startup handlers to the provided ``FastAPI`` app.

    When the native registry router is included in another application, the
    startup event defined on the standalone ``app`` in this module will not be
    executed. Exposing this helper lets the main application register the same
    initialization logic, ensuring the schema and seed data exist before any
    requests are handled.
    """

    @app.on_event("startup")
    def on_startup() -> None:  # pragma: no cover - executed at runtime
        Base.metadata.create_all(engine)
        with SessionLocal() as db:
            seed_taxonomy(db)


# When running this module directly, ensure events are registered for ``app``
register_events(app)


# -----------------------------------------------------------------------------
# Seed taxonomy (Gaming & Non-Gaming)
# -----------------------------------------------------------------------------

def get_or_create_category(db: Session, name: str, description: str = "") -> Category:
    slug = slugify(name)
    cat = db.query(Category).filter_by(slug=slug).one_or_none()
    if not cat:
        cat = Category(name=name, slug=slug, description=description)
        db.add(cat)
        db.commit()
        db.refresh(cat)
    return cat


def create_subcategories(db: Session, cat: Category, names: List[str]):
    for n in names:
        slug = slugify(n)
        exists = (
            db.query(SubCategory)
            .filter(SubCategory.category_id == cat.id, SubCategory.slug == slug)
            .one_or_none()
        )
        if not exists:
            db.add(SubCategory(category_id=cat.id, name=n, slug=slug))
    db.commit()


def seed_taxonomy(db: Session):
    # Gaming
    gaming = get_or_create_category(db, "Gaming", "All tribal gaming enterprises")
    create_subcategories(db, gaming, [
        "Class I — Traditional/Social Games",
        "Class II — Bingo & Non-banked Card Rooms",
        "Class III — Casino Gaming",
        # Class III details as separate discoverable facets
        "Slots",
        "Electronic Gaming Machines",
        "Blackjack",
        "Baccarat",
        "Roulette",
        "Craps",
        "Poker Rooms",
        "Keno",
        "Sports Betting",
        "Horse Racing / Simulcast",
        "Lotteries",
        "Bingo",
        # Emerging
        "Esports Wagering",
        "Daily Fantasy Sports",
        "Online Poker",
        "Online Casino"
    ])

    # Non-Gaming
    nongaming = get_or_create_category(db, "Non-Gaming", "All other Native enterprises")
    create_subcategories(db, nongaming, [
        "Cannabis",
        "Liquor / Breweries / Distilleries / Wineries",
        "Tobacco / Smoke Shops",
        "Fireworks",
        "Arts & Makers",
        "Carvers",
        "Writers",
        "Podcasts",
        "TV / Film",
        "Hunting & Fisheries",
        "Museums & Cultural Centers",
        "Docks & Waterfront",
        "Convenience Stores",
        "Enterprises / Corporate Holdings",
        "Gas Stations",
        "Utilities & Infrastructure",
        "Clothing / Fashion Brands",
        "Business Centers",
    ])


# -----------------------------------------------------------------------------
# ROUTES — Public browsing (server-rendered examples)
# -----------------------------------------------------------------------------
@app.get("/")
def home(request: Request, db: Session = Depends(get_db)):
    categories = db.query(Category).order_by(Category.name).all()
    return templates.TemplateResponse("home.html", {"request": request, "categories": categories})


@app.get("/c/{category_slug}")
def view_category(category_slug: str, request: Request, db: Session = Depends(get_db)):
    cat = db.query(Category).filter_by(slug=category_slug).one_or_none()
    if not cat:
        raise HTTPException(404, "Category not found")
    subcats = db.query(SubCategory).filter_by(category_id=cat.id).order_by(SubCategory.name).all()
    return templates.TemplateResponse("category.html", {"request": request, "category": cat, "subcategories": subcats})


@app.get("/s/{subcategory_slug}")
def view_subcategory(subcategory_slug: str, request: Request, db: Session = Depends(get_db)):
    sub = db.query(SubCategory).filter_by(slug=subcategory_slug).one_or_none()
    if not sub:
        raise HTTPException(404, "Subcategory not found")
    # list businesses tagged with this subcategory
    bs_ids = [bs.business_id for bs in db.query(BusinessSubCategory).filter_by(subcategory_id=sub.id).all()]
    businesses = []
    if bs_ids:
        businesses = (
            db.query(Business)
            .filter(Business.id.in_(bs_ids))
            .order_by(Business.name)
            .all()
        )
    return templates.TemplateResponse("subcategory.html", {"request": request, "subcategory": sub, "businesses": businesses})


@app.get("/b/{slug}")
def view_business(slug: str, request: Request, db: Session = Depends(get_db)):
    biz = db.query(Business).filter_by(slug=slug).one_or_none()
    if not biz:
        raise HTTPException(404, "Business not found")
    avg = None
    if biz.reviews:
        avg = round(sum(r.rating for r in biz.reviews if r.status == ReviewStatus.approved) / max(1, len([r for r in biz.reviews if r.status == ReviewStatus.approved])), 2)
    return templates.TemplateResponse("business.html", {
        "request": request,
        "business": biz,
        "avg_rating": avg,
        "reviews": [r for r in biz.reviews if r.status == ReviewStatus.approved],
        "media": biz.media,
        "legal_links": biz.links,
        "compliance": biz.compliance,
        "size_feedback": biz.size_feedback,
    })


# -----------------------------------------------------------------------------
# ROUTES — JSON API (for async forms or future React)
# -----------------------------------------------------------------------------
@app.post("/api/business", response_model=BusinessOut)
def create_business(payload: BusinessCreate, db: Session = Depends(get_db)):
    slug = payload.slug or slugify(payload.name)
    if db.query(Business).filter_by(slug=slug).one_or_none():
        raise HTTPException(400, "Slug already in use")

    biz = Business(
        name=payload.name,
        slug=slug,
        description=payload.description,
        tribe_id=payload.tribe_id,
        owner_type=payload.owner_type,
        website=payload.website,
        email=payload.email,
        phone=payload.phone,
        street=payload.street,
        city=payload.city,
        state=payload.state,
        postal_code=payload.postal_code,
        country=payload.country,
        latitude=payload.latitude,
        longitude=payload.longitude,
    )
    db.add(biz)
    db.flush()

    for sid in payload.subcategory_ids:
        db.add(BusinessSubCategory(business_id=biz.id, subcategory_id=sid))

    db.commit()
    db.refresh(biz)
    return BusinessOut(id=biz.id, name=biz.name, slug=biz.slug, description=biz.description)


@app.get("/api/business")
def list_businesses(
    q: Optional[str] = Query(None, description="search by name/desc"),
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    db: Session = Depends(get_db),
):
    qry = db.query(Business)
    if q:
        like = f"%{q.lower()}%"
        qry = qry.filter((Business.name.ilike(like)) | (Business.description.ilike(like)))

    if subcategory:
        sub = db.query(SubCategory).filter_by(slug=subcategory).one_or_none()
        if sub:
            ids = [bs.business_id for bs in db.query(BusinessSubCategory).filter_by(subcategory_id=sub.id).all()]
            if ids:
                qry = qry.filter(Business.id.in_(ids))
            else:
                qry = qry.filter(False)
    elif category:
        cat = db.query(Category).filter_by(slug=category).one_or_none()
        if cat:
            sub_ids = [s.id for s in db.query(SubCategory).filter_by(category_id=cat.id)]
            bs_ids = [bs.business_id for bs in db.query(BusinessSubCategory).filter(BusinessSubCategory.subcategory_id.in_(sub_ids))]
            if bs_ids:
                qry = qry.filter(Business.id.in_(bs_ids))
            else:
                qry = qry.filter(False)

    items = qry.order_by(Business.name).all()
    out = []
    for b in items:
        ratings = [r.rating for r in b.reviews if r.status == ReviewStatus.approved]
        avg = round(sum(ratings)/len(ratings), 2) if ratings else None
        out.append(BusinessOut(id=b.id, name=b.name, slug=b.slug, description=b.description, avg_rating=avg))
    return out


@app.post("/api/b/{slug}/reviews")
def create_review(slug: str, payload: ReviewCreate, request: Request, db: Session = Depends(get_db)):
    biz = db.query(Business).filter_by(slug=slug).one_or_none()
    if not biz:
        raise HTTPException(404, "Business not found")
    # In prod, resolve user from auth; here we allow anonymous (user_id=None)
    review = Review(business_id=biz.id, title=payload.title, body=payload.body, rating=payload.rating)
    db.add(review)
    db.commit()
    return {"ok": True, "status": review.status}


@app.post("/api/b/{slug}/size-feedback")
def add_size_feedback(slug: str, payload: SizeFeedbackCreate, db: Session = Depends(get_db)):
    biz = db.query(Business).filter_by(slug=slug).one_or_none()
    if not biz:
        raise HTTPException(404, "Business not found")
    sf = SizeFeedback(business_id=biz.id, **payload.model_dump())
    db.add(sf)
    db.commit()
    return {"ok": True}


# Minimal moderation endpoints (for admins/moderators)
@app.post("/api/reviews/{review_id}/moderate")
def moderate_review(review_id: int, status: ReviewStatus, db: Session = Depends(get_db)):
    r = db.query(Review).get(review_id)
    if not r:
        raise HTTPException(404, "Review not found")
    r.status = status
    db.commit()
    return {"ok": True}


# -----------------------------------------------------------------------------
# Templates (inline examples – move to /templates)
# -----------------------------------------------------------------------------
# home.html
home_html = """
{% extends 'layout.html' %}
{% block content %}
<div class="container py-4">
  <h1 class="mb-3">Native-Owned Business Registry & TERO Hub</h1>
  <div class="row">
    {% for c in categories %}
      <div class="col-md-6 mb-3">
        <div class="card h-100">
          <div class="card-body">
            <h3 class="card-title"><a href="/c/{{ c.slug }}">{{ c.name }}</a></h3>
            <p class="card-text">{{ c.description }}</p>
          </div>
        </div>
      </div>
    {% endfor %}
  </div>
</div>
{% endblock %}
"""

# category.html
category_html = """
{% extends 'layout.html' %}
{% block content %}
<div class="container py-4">
  <h2 class="mb-3">{{ category.name }}</h2>
  <div class="list-group">
    {% for s in subcategories %}
      <a class="list-group-item list-group-item-action" href="/s/{{ s.slug }}">{{ s.name }}</a>
    {% endfor %}
  </div>
</div>
{% endblock %}
"""

# subcategory.html
subcategory_html = """
{% extends 'layout.html' %}
{% block content %}
<div class="container py-4">
  <h2 class="mb-3">{{ subcategory.name }}</h2>
  {% if businesses %}
    <div class="list-group">
      {% for b in businesses %}
        <a class="list-group-item list-group-item-action" href="/b/{{ b.slug }}">
          <div class="d-flex justify-content-between">
            <h5 class="mb-1">{{ b.name }}</h5>
            <small>{{ b.city }}{% if b.state %}, {{ b.state }}{% endif %}</small>
          </div>
          <p class="mb-1">{{ (b.description or '')[:160] }}{% if (b.description or '')|length > 160 %}…{% endif %}</p>
        </a>
      {% endfor %}
    </div>
  {% else %}
    <p>No businesses listed yet.</p>
  {% endif %}
</div>
{% endblock %}
"""

# business.html
business_html = """
{% extends 'layout.html' %}
{% block content %}
<div class="container py-4">
  <div class="row">
    <div class="col-md-7">
      <h2 class="mb-2">{{ business.name }}</h2>
      <p>{{ business.description }}</p>

      <h5 class="mt-4">Compliance & Legal</h5>
      <ul>
        {% for c in compliance %}
          <li><strong>{{ c.key }}:</strong> {{ c.value }}</li>
        {% endfor %}
      </ul>
      <ul>
        {% for l in legal_links %}
          <li><a href="{{ l.url }}" target="_blank" rel="noopener">{{ l.label }}</a></li>
        {% endfor %}
      </ul>

      <h5 class="mt-4">Community Reviews {% if avg_rating %}<span class="badge bg-success">Avg {{ avg_rating }}</span>{% endif %}</h5>
      {% if reviews %}
        {% for r in reviews %}
          <div class="border rounded p-3 mb-2">
            <strong>{{ r.title }}</strong> — {{ r.rating }}/5
            <div class="text-muted small">{{ r.created_at }}</div>
            <div>{{ r.body }}</div>
          </div>
        {% endfor %}
      {% else %}
        <p>No reviews yet.</p>
      {% endif %}

      <form class="mt-3" id="review-form">
        <h6>Add a Review</h6>
        <input class="form-control mb-2" name="title" placeholder="Title" required>
        <textarea class="form-control mb-2" name="body" placeholder="Your experience" required></textarea>
        <input class="form-control mb-2" name="rating" type="number" min="1" max="5" value="5" required>
        <button class="btn btn-primary">Submit</button>
      </form>

      <h5 class="mt-4">Clothing Fit & Cultural Notes</h5>
      {% if size_feedback %}
        {% for s in size_feedback %}
          <div class="border rounded p-3 mb-2">
            <div class="small text-muted">{{ s.created_at }}</div>
            <div><strong>{{ s.product_name or 'Product' }}</strong> — Fit scale: {{ s.fit_scale }} (-2 small … +2 large)</div>
            {% if s.usual_size or s.purchased_size %}
              <div>Usual size: {{ s.usual_size }} | Purchased: {{ s.purchased_size }}</div>
            {% endif %}
            {% if s.fit_notes %}<div>{{ s.fit_notes }}</div>{% endif %}
            {% if s.culture_notes %}<div class="mt-1"><em>Cultural:</em> {{ s.culture_notes }}</div>{% endif %}
          </div>
        {% endfor %}
      {% else %}
        <p>No size feedback yet.</p>
      {% endif %}

      <form class="mt-2" id="size-form">
        <input class="form-control mb-2" name="product_name" placeholder="Product name (optional)">
        <div class="row g-2">
          <div class="col"><input class="form-control" name="usual_size" placeholder="Your usual size"></div>
          <div class="col"><input class="form-control" name="purchased_size" placeholder="Purchased size"></div>
        </div>
        <textarea class="form-control my-2" name="fit_notes" placeholder="Fit notes (e.g., chest tight, sleeves long)"></textarea>
        <label class="form-label">Fit scale (-2 small … +2 large)</label>
        <input class="form-range" name="fit_scale" type="range" min="-2" max="2" value="0">
        <textarea class="form-control my-2" name="culture_notes" placeholder="Cultural significance (story, pattern, practice)"></textarea>
        <button class="btn btn-outline-primary">Submit</button>
      </form>
    </div>
    <div class="col-md-5">
      <div id="gallery" class="mb-3">
        {% if media %}
          {% for m in media %}
            <img class="img-fluid mb-2 rounded" src="{{ m.url }}" alt="{{ m.caption }}">
          {% endfor %}
        {% else %}
          <div class="alert alert-info">No photos yet.</div>
        {% endif %}
      </div>
      <div class="card">
        <div class="card-body">
          <h6>Contact</h6>
          {% if business.website %}<div><a href="{{ business.website }}" target="_blank">Website</a></div>{% endif %}
          {% if business.email %}<div>Email: {{ business.email }}</div>{% endif %}
          {% if business.phone %}<div>Phone: {{ business.phone }}</div>{% endif %}
          <div class="small text-muted mt-2">{{ business.street }} {{ business.city }} {{ business.state }} {{ business.postal_code }}</div>
        </div>
      </div>
    </div>
  </div>
</div>
<script>
  const postJSON = async (url, data) => {
    const r = await fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)});
    return await r.json();
  }
  document.getElementById('review-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(e.target));
    data.rating = parseInt(data.rating, 10);
    const res = await postJSON('/api/b/{{ business.slug }}/reviews', data);
    alert('Review submitted for moderation.');
    location.reload();
  });
  document.getElementById('size-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(e.target));
    data.fit_scale = parseInt(data.fit_scale, 10);
    const res = await postJSON('/api/b/{{ business.slug }}/size-feedback', data);
    alert('Thanks for your fit & cultural notes!');
    location.reload();
  });
</script>
{% endblock %}
"""

# layout.html
layout_html = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Native Registry</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body>
<nav class="navbar navbar-expand-lg bg-body-tertiary">
  <div class="container">
    <a class="navbar-brand" href="/">Native Registry</a>
  </div>
</nav>
<main>
  {% block content %}{% endblock %}
</main>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

# -----------------------------------------------------------------------------
# Helper to materialize templates to disk on startup (dev convenience)
# -----------------------------------------------------------------------------

TEMPLATE_DIR = os.path.join(os.getcwd(), "templates")
os.makedirs(TEMPLATE_DIR, exist_ok=True)

with open(os.path.join(TEMPLATE_DIR, "layout.html"), "w", encoding="utf-8") as f:
    f.write(layout_html)
with open(os.path.join(TEMPLATE_DIR, "home.html"), "w", encoding="utf-8") as f:
    f.write(home_html)
with open(os.path.join(TEMPLATE_DIR, "category.html"), "w", encoding="utf-8") as f:
    f.write(category_html)
with open(os.path.join(TEMPLATE_DIR, "subcategory.html"), "w", encoding="utf-8") as f:
    f.write(subcategory_html)
with open(os.path.join(TEMPLATE_DIR, "business.html"), "w", encoding="utf-8") as f:
    f.write(business_html)


# -----------------------------------------------------------------------------
# Quick how-to (dev)
# -----------------------------------------------------------------------------
"""
Run locally (dev):

python -m uvicorn app:app --reload --port 8000

- Home lists categories (Gaming / Non-Gaming)
- Category page lists subcategories
- Subcategory page lists businesses tied to that subcategory
- Business page shows photos, reviews (approved only), compliance + legal links, and clothing fit + cultural notes; includes forms to submit new review/fit notes via JSON endpoints (moderated)

Add a business via JSON:

curl -X POST http://localhost:8000/api/business \
  -H 'Content-Type: application/json' \
  -d '{
    "name":"Snoqualmie Casino",
    "slug":"snoqualmie-casino",
    "description":"Class III casino with slots, table games, and sportsbook.",
    "owner_type":"tribal_enterprise",
    "website":"https://example.com",
    "subcategory_ids":[
        # e.g., ids for "Class III — Casino Gaming", "Slots", "Blackjack", "Sports Betting"
    ]
  }'

Moderate a review (approve):

curl -X POST 'http://localhost:8000/api/reviews/1/moderate?status=approved'

Schema extensibility:
- To add a new subcategory (e.g., "Craps" already included), just insert into `subcategories` with the `category_id` for Gaming.
- To track legality per jurisdiction, add a table `jurisdictions` and a join table `subcategory_legality` mapping subcategory -> jurisdiction -> status/link.

Security notes:
- Plug in auth (e.g., OAuth or session) and check `User.role` before allowing moderation endpoints.
- Add rate limiting & spam protection (honeypot field, simple token, or captcha) for public forms.
"""
