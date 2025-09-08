from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .appy import (
    Category,
    SubCategory,
    Business,
    BusinessSubCategory,
    ReviewStatus,
    templates,
    get_db,
    Base,
    engine,
    SessionLocal,
    seed_taxonomy,
)

router = APIRouter(prefix="/native-registry", tags=["native_registry"])


@router.on_event("startup")
def init_schema():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_taxonomy(db)


@router.get("")
def home(request: Request, db: Session = Depends(get_db)):
    categories = db.query(Category).order_by(Category.name).all()
    return templates.TemplateResponse("home.html", {"request": request, "categories": categories})


@router.get("/c/{category_slug}")
def view_category(category_slug: str, request: Request, db: Session = Depends(get_db)):
    cat = db.query(Category).filter_by(slug=category_slug).one_or_none()
    if not cat:
        raise HTTPException(404, "Category not found")
    subcats = (
        db.query(SubCategory)
        .filter_by(category_id=cat.id)
        .order_by(SubCategory.name)
        .all()
    )
    return templates.TemplateResponse(
        "category.html", {"request": request, "category": cat, "subcategories": subcats}
    )


@router.get("/s/{subcategory_slug}")
def view_subcategory(
    subcategory_slug: str, request: Request, db: Session = Depends(get_db)
):
    sub = db.query(SubCategory).filter_by(slug=subcategory_slug).one_or_none()
    if not sub:
        raise HTTPException(404, "Subcategory not found")
    bs_ids = [
        bs.business_id
        for bs in db.query(BusinessSubCategory).filter_by(subcategory_id=sub.id).all()
    ]
    businesses = []
    if bs_ids:
        businesses = (
            db.query(Business)
            .filter(Business.id.in_(bs_ids))
            .order_by(Business.name)
            .all()
        )
    return templates.TemplateResponse(
        "subcategory.html",
        {"request": request, "subcategory": sub, "businesses": businesses},
    )


@router.get("/b/{slug}")
def view_business(slug: str, request: Request, db: Session = Depends(get_db)):
    biz = db.query(Business).filter_by(slug=slug).one_or_none()
    if not biz:
        raise HTTPException(404, "Business not found")
    avg = None
    if biz.reviews:
        avg = round(
            sum(r.rating for r in biz.reviews if r.status == ReviewStatus.approved)
            / max(
                1,
                len([r for r in biz.reviews if r.status == ReviewStatus.approved]),
            ),
            2,
        )
    return templates.TemplateResponse(
        "business.html",
        {
            "request": request,
            "business": biz,
            "avg_rating": avg,
            "reviews": [r for r in biz.reviews if r.status == ReviewStatus.approved],
            "media": biz.media,
            "legal_links": biz.links,
            "compliance": biz.compliance,
            "size_feedback": biz.size_feedback,
        },
    )
