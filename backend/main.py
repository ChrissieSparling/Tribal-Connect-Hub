# backend/main.py — streamlined and de-duped
from __future__ import annotations

import os
import secrets
import traceback
import qrcode
import io
from pathlib import Path
from datetime import date
from typing import Dict, List, Generator
from contextlib import contextmanager, suppress

from fastapi import FastAPI, Request, Form, Depends, status, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from fastapi.responses import RedirectResponse, HTMLResponse, StreamingResponse

from sqlalchemy.orm import Session as SASession
from sqlalchemy.exc import IntegrityError

# 🔐 Auth helpers
# from app.common.auth import hash_password, safe_verify_password, validate_password
from backend.app.common.auth import (
    hash_password,
    safe_verify_password,
    validate_password,
)

# ---- Routers (align to your tree)
from backend.app.api import api_router
from backend.tribal_core import (
    # router as core_router,
    register_events as core_register,
    get_db as core_get_db,
    User,
)
from backend.native_registry.appy import (
    register_events as native_registry_register,
)

# Your ORM User (from your SQLAlchemy models package; if it's the one in tribal_core, import from there)
# from .models import User  # <- switch duplicate and merge into .tribal_core.py
# from tribal_core import User

from pydantic import BaseModel  # after FastAPI to avoid confusion

# ---------------------- FIXED CONTEXT MANAGER ----------------------
# @contextmanager
# def db_session() -> Generator[SASession, None, None]:
#     """Use a DB session outside of FastAPI dependency injection."""
#     gen = core_get_db()      # FastAPI dependency generator that yields a Session
#     db = next(gen)           # get the Session instance
#     try:
#         yield db             # hand it to caller
#     finally:
#         # ensure generator cleanup runs (close session)
#         with suppress(StopIteration):
#             next(gen)
# # ------------------------------------------------------------------

# BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# STATIC_DIR = os.path.join(BASE_DIR, "static")
# TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

# ---- Paths
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"


# ---- App
app = FastAPI(title="Tribal Connect Hub", version="0.1.0")
app.include_router(api_router)

# Sessions
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SESSION_SECRET", secrets.token_hex(32)),
    max_age=60 * 60 * 24 * 7,  # 7 days
    same_site="lax",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: restrict in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static + templates
# if os.path.isdir(STATIC_DIR):
#     app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# ---- Static & Templates
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# DB/table creation + seeding at startup (from core and native registry)
core_register(app)
native_registry_register(app)


# ---------- Pydantic view models for in-memory demo endpoints ----------


class Tribe(BaseModel):
    id: int
    name: str
    description: str
    public_sharing: Dict[str, bool]


class Event(BaseModel):
    id: int
    title: str
    description: str
    date: date
    tribe_id: int


class Law(BaseModel):
    id: int
    title: str
    summary: str
    date_passed: date
    tribe_id: int


class Member(BaseModel):
    id: int
    first_name: str
    last_name: str
    role: str
    tribe_id: int
    profile_picture_url: str | None = None
    website_url: str | None = None
    bio: str | None = None


# ---------- In-memory demo data ----------
tribes: Dict[int, Tribe] = {
    1: Tribe(
        id=1,
        name="Snoqualmie Tribe",
        description="Honoring the People of the Moon",
        public_sharing={"laws": True, "events": True, "members": False},
    ),
    2: Tribe(
        id=2,
        name="Tulalip Tribes",
        description="Strong Coast Salish presence rooted in tradition and growth.",
        public_sharing={"laws": False, "events": True, "members": False},
    ),
    3: Tribe(
        id=3,
        name="Yakama Nation",
        description="Stewards of river lands and plateau regions of Central WA.",
        public_sharing={"laws": False, "events": True, "members": False},
    ),
}

events: List[Event] = [
    Event(
        id=1,
        title="First Canoe Landing",
        description="Welcoming the canoes at the river mouth",
        date=date(2025, 8, 1),
        tribe_id=1,
    ),
    Event(
        id=2,
        title="Fall Gathering",
        description="Celebration with drumming, stories, and food",
        date=date(2025, 10, 15),
        tribe_id=1,
    ),
]

laws: List[Law] = [
    Law(
        id=1,
        title="Fishing Rights Ordinance",
        summary="Defines the fishing rights within ancestral waters.",
        date_passed=date(2020, 5, 10),
        tribe_id=1,
    ),
    Law(
        id=2,
        title="Cultural Site Protection Act",
        summary="Protects sacred lands and burial sites from development.",
        date_passed=date(2021, 9, 1),
        tribe_id=1,
    ),
]

members: List[Member] = [
    Member(
        id=1,
        first_name="Glaysia",
        last_name="Sparling",
        role="Youth",
        tribe_id=1202,
        profile_picture_url="https://example.com/images/glaysia.jpg",
        website_url="https://glaysiaspeaks.com",
        bio="Recent graduate passionate about Indigenous health and youth leadership.",
    ),
    Member(
        id=2,
        first_name="Sharon",
        last_name="Frelinger",
        role="Elder",
        tribe_id=195,
        profile_picture_url="https://example.com/images/sharon.jpg",
        website_url="https://sharonfrelinger.com",
        bio="completely awesome.",
    ),
    Member(
        id=3,
        first_name="Chrissie",
        last_name="Sparling",
        role="Tribal Council",
        tribe_id=875,
        profile_picture_url="https://example.com/images/chrissie.jpg",
        website_url="https://chrissiesparling.com",
        bio="happy and in love with life.",
    ),
    Member(
        id=4,
        first_name="Aurrick",
        last_name="Sparling",
        role="Tribal Member",
        tribe_id=1203,
        profile_picture_url="https://example.com/images/aurrick.jpg",
        website_url="https://aurricksvision.com",
        bio="advocating for those who are still looking to find their way.",
    ),
    Member(
        id=5,
        first_name="Joseph",
        last_name="Willoughby",
        role="Tribal Member Employee",
        tribe_id=1203,
        profile_picture_url="https://example.com/images/Joseph.jpg",
        website_url="https://joesvision.com",
        bio="advocating for IT.",
    ),
]


# ---------- Helpers ----------
def check_permission(tribe_id: int, section: str):
    tribe = tribes.get(tribe_id)
    if not tribe:
        raise HTTPException(status_code=404, detail="Tribe not found")
    if not tribe.public_sharing.get(section, False):
        raise HTTPException(
            status_code=403,
            detail=f"This tribe has chosen not to publicly share their {section}.",
        )


def get_current_user(request: Request, db: SASession):
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.query(User).filter(User.id == user_id).first()


def require_admin(request: Request, db: SASession):
    user = get_current_user(request, db)
    if not user or user.role not in ("admin", "enrollment"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admins only."
        )
    return user


# ---------- Routes (API / JSON) ----------


@app.get("/tribes", response_model=List[Tribe])
def get_all_tribes():
    return list(tribes.values())


@app.get("/tribes/{tribe_id}", response_model=Tribe)
def get_tribe(tribe_id: int):
    tribe = tribes.get(tribe_id)
    if not tribe:
        raise HTTPException(status_code=404, detail="Tribe not found")
    return tribe


@app.get("/tribes/{tribe_id}/events", response_model=List[Event])
def get_tribe_events(tribe_id: int):
    check_permission(tribe_id, "events")
    return [e for e in events if e.tribe_id == tribe_id]


@app.get("/tribes/{tribe_id}/laws", response_model=List[Law])
def get_tribe_laws(tribe_id: int):
    check_permission(tribe_id, "laws")
    return [l for l in laws if l.tribe_id == tribe_id]


@app.get("/tribes/{tribe_id}/members", response_model=List[Member])
def get_tribe_members(tribe_id: int):
    check_permission(tribe_id, "members")
    return [m for m in members if m.tribe_id == tribe_id]


# ---------- Routes (HTML / Templates) ----------
@app.get("/", response_class=HTMLResponse)
async def home_page(request: Request):
    return templates.TemplateResponse("home.html", {"request": request})


@app.get("/tribes-html", response_class=HTMLResponse)
async def tribe_list_page(request: Request):
    return templates.TemplateResponse("tribe_list.html", {"request": request})


@app.get("/tribes-html/{tribe_id}", response_class=HTMLResponse)
async def tribe_detail_page(request: Request, tribe_id: int):
    return templates.TemplateResponse(
        "tribe_detail.html", {"request": request, "tribe_id": tribe_id}
    )


@app.get("/events-html/{event_id}/share", response_class=HTMLResponse)
async def event_share_page(request: Request, event_id: int):
    return templates.TemplateResponse(
        "event_share.html", {"request": request, "event_id": event_id}
    )


@app.get("/registry", response_class=HTMLResponse)
async def registry_page(request: Request):
    # If you have categories, pass them here; otherwise an empty list is fine.
    return templates.TemplateResponse(
        "registry.html", {"request": request, "categories": []}
    )


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: SASession = Depends(core_get_db),
):
    user = db.query(User).filter(User.email == email).first()
    if not user or not safe_verify_password(password, user.password):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid email or password."},
            status_code=401,
        )
    # ✅ set session and redirect (only once)
    request.session["user_id"] = user.id
    return RedirectResponse(url="/welcome", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)


@app.get("/members", response_class=HTMLResponse)
async def members_page(request: Request):
    return templates.TemplateResponse("members.html", {"request": request})


@app.get("/departments", response_class=HTMLResponse)
async def departments_page(request: Request):
    return templates.TemplateResponse("departments.html", {"request": request})


@app.get("/businesses", response_class=HTMLResponse)
async def businesses_page(request: Request):
    return templates.TemplateResponse("businesses.html", {"request": request})


@app.get("/tribes-admin", response_class=HTMLResponse)
async def tribes_admin_page(request: Request):
    return templates.TemplateResponse("tribes_admin.html", {"request": request})


@app.get("/signup", response_class=HTMLResponse)
async def signup_form(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request})


# If you have validate_password/hash_password, keep; otherwise comment this entire endpoint for now.
# from .auth import validate_password, hash_password  # uncomment if implemented


@app.post("/signup")
async def signup(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: SASession = Depends(core_get_db),
):
    # Server-side password enforcement
    if not validate_password(password):
        return templates.TemplateResponse(
            "signup.html",
            {
                "request": request,
                "error": (
                    "Password must be 8+ chars and include uppercase, "
                    "lowercase, number, and special character."
                ),
                "name": name,
                "email": email,
            },
            status_code=400,
        )
    try:
        # Optional duplicate check…
        # existing = db.query(User).filter(User.email == email).first()
        # if existing:
        #     return templates.TemplateResponse(...)

        hashed_pw = hash_password(password)
        user = User(username=name, email=email, password=hashed_pw)
        db.add(user)
        db.commit()
        db.refresh(user)
        request.session["user_id"] = user.id
        return RedirectResponse(url="/welcome", status_code=303)

    except IntegrityError:
        db.rollback()
        return templates.TemplateResponse(
            "signup.html",
            {
                "request": request,
                "error": "That name or email is already in use.",
                "name": name,
                "email": email,
            },
            status_code=400,
        )
    except Exception as e:
        db.rollback()
        print("SIGNUP ERROR:", e)
        traceback.print_exc()
        return templates.TemplateResponse(
            "signup.html",
            {
                "request": request,
                "error": "Something went wrong while creating your account.",
                "name": name,
                "email": email,
            },
            status_code=500,
        )


@app.get("/welcome", response_class=HTMLResponse)
async def welcome_page(request: Request, db: SASession = Depends(core_get_db)):
    current_user = get_current_user(request, db)
    return templates.TemplateResponse(
        "welcome.html", {"request": request, "current_user": current_user}
    )


@app.post("/onboarding/tribe")
async def onboarding_tribe(
    request: Request,
    tribe_id: int = Form(...),
    tribal_id_number: str = Form(None),
    db: SASession = Depends(core_get_db),
):
    user = get_current_user(request, db)
    if not user:
        return templates.TemplateResponse(
            "welcome.html",
            {
                "request": request,
                "error": "Please sign in first.",
                "current_user": None,
            },
            status_code=401,
        )

    user.tribe_id = tribe_id
    user.tribal_id_number = (tribal_id_number or "").strip() or None
    db.add(user)
    db.commit()
    db.refresh(user)

    return templates.TemplateResponse(
        "welcome.html",
        {
            "request": request,
            "current_user": user,
            "message": "Saved. You’ll see more once your membership is verified.",
        },
    )


@app.get("/admin/memberships", response_class=HTMLResponse)
async def admin_memberships(request: Request, db: SASession = Depends(core_get_db)):
    require_admin(request, db)
    pending = (
        db.query(User)
        .filter(User.is_verified == False, User.tribe_id != None)
        .order_by(User.id.asc())
        .all()
    )
    return templates.TemplateResponse(
        "admin_membership.html", {"request": request, "pending": pending}
    )


@app.post("/admin/memberships/{user_id}/approve")
async def admin_approve_membership(
    request: Request, user_id: int, db: SASession = Depends(core_get_db)
):
    require_admin(request, db)
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    u.is_verified = True
    db.commit()
    return RedirectResponse(url="/admin/memberships", status_code=303)


@app.post("/admin/memberships/{user_id}/deny")
async def admin_deny_membership(
    request: Request, user_id: int, db: SASession = Depends(core_get_db)
):
    require_admin(request, db)
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    u.tribe_id = None
    u.tribal_id_number = None
    u.is_verified = False
    db.commit()
    return RedirectResponse(url="/admin/memberships", status_code=303)


@app.get("/qrcode")
def get_qr(data: str = "Hello TribalConnect"):
    qr = qrcode.make(data)
    buf = io.BytesIO()
    qr.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")
