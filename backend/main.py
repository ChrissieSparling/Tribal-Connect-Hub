# main.py
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Dict, List
from datetime import date
from fastapi.middleware.cors import CORSMiddleware
import os
# pull in the router + startup hook
from tribal_core import router as core_router, register_events as core_register

# ----- Paths (absolute = fewer surprises)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

app = FastAPI(title="Tribal Connect Hub")

# ✅ allow PATCH/DELETE and handle OPTIONS preflight
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],           # tighten later to your domain
    allow_credentials=True,
    allow_methods=["*"],           # or ["GET","POST","PATCH","DELETE","OPTIONS"]
    allow_headers=["*"],
)
# Static + templates
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# 🔗 Include the Tribal Core API under /api to avoid path collisions
app.include_router(core_router, prefix="/api")

# 🔧 Register DB/table creation + seeding at startup
core_register(app)

# ---------- Models ----------
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

# ---------- Data ----------
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
    Event(id=1, title="First Canoe Landing", description="Welcoming the canoes at the river mouth",
        date=date(2025, 8, 1), tribe_id=1),
    Event(id=2, title="Fall Gathering", description="Celebration with drumming, stories, and food",
        date=date(2025, 10, 15), tribe_id=1),
]

laws: List[Law] = [
    Law(id=1, title="Fishing Rights Ordinance",
        summary="Defines the fishing rights within ancestral waters.",
        date_passed=date(2020, 5, 10), tribe_id=1),
    Law(id=2, title="Cultural Site Protection Act",
        summary="Protects sacred lands and burial sites from development.",
        date_passed=date(2021, 9, 1), tribe_id=1),
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
        bio="Recent graduate passionate about Indigenous health and youth leadership."
        ),
    Member(
        id=2,
        first_name="Sharon",
        last_name="Frelinger",
        role="Elder",
        tribe_id=195,
        profile_picture_url="https://example.com/images/sharon.jpg",
        website_url="https://sharonfrelinger.com",
        bio="completely awesome."
        ),
    Member(
        id=3,
        first_name="Chrissie",
        last_name="Sparling",
        role="TribalCouncil",
        tribe_id=875,
        profile_picture_url="https://example.com/images/chrissie.jpg",
        website_url="https://chrissiesparling.com",
        bio="happy and in love with life."
        ),
    Member(
        id=4,
        first_name="Aurrick",
        last_name="Sparling",
        role="Tribal Member",
        tribe_id=1203,
        profile_picture_url="https://example.com/images/aurrick.jpg",
        website_url="https://aurricksvision.com",
        bio="advocating for those who are still looking to find their way."),
    Member(
        id=5,
        first_name="Joseph",
        last_name="Willoughby",
        role="Tribal Member",
        tribe_id=1203,
        profile_picture_url="https://example.com/images/Joseph.jpg",
        website_url="https://joesvision.com",
        bio="advocating for IT."),
]

# ---------- Helpers ----------
def check_permission(tribe_id: int, section: str):
    tribe = tribes.get(tribe_id)
    if not tribe:
        raise HTTPException(status_code=404, detail="Tribe not found")
    if not tribe.public_sharing.get(section, False):
        raise HTTPException(status_code=403, detail=f"This tribe has chosen not to publicly share their {section}.")

# ---------- Routes ----------
@app.get("/health")
def health():
    return {"ok": True}

@app.get("/", response_class=HTMLResponse)
def homepage(request: Request):
    return templates.TemplateResponse("home.html", {"request": request})

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

@app.get("/tribes-html", response_class=HTMLResponse)
def tribe_list_view(request: Request):
    return templates.TemplateResponse("tribe_list.html", {"request": request, "tribes": tribes.values()})

@app.get("/tribes-html/{tribe_id}", response_class=HTMLResponse)
def tribe_detail_page(request: Request, tribe_id: int):
    return templates.TemplateResponse("tribe_detail.html", {"request": request, "tribe_id": tribe_id})

@app.get("/events-html/{event_id}/share", response_class=HTMLResponse)
def event_share_page(request: Request, event_id: int):
    return templates.TemplateResponse("event_share.html", {"request": request, "event_id": event_id})


