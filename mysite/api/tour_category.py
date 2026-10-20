
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from mysite.database.db import get_db
from mysite.database.models import TourCategory
from mysite.database.schema import (
    TourCategoryInputSchema,
    TourCategoryUpdateSchema,
    TourCategoryOutSchema
)


category_router = APIRouter(
    prefix="/tour-categories",
    tags=["Tour Categories"]
)


@category_router.post("/", response_model=TourCategoryOutSchema)
def create_category(
    category: TourCategoryInputSchema,
    db: Session = Depends(get_db)
):
    category_db = TourCategory(**category.model_dump())

    db.add(category_db)
    db.commit()
    db.refresh(category_db)

    return category_db


@category_router.get("/", response_model=list[TourCategoryOutSchema])
def list_category(db: Session = Depends(get_db)):
    return db.query(TourCategory).all()


@category_router.get("/{category_id}/", response_model=TourCategoryOutSchema)
def detail_category(
    category_id: int,
    db: Session = Depends(get_db)
):
    category_db = db.get(TourCategory, category_id)

    if category_db is None:
        raise HTTPException(
            status_code=404,
            detail="Категория табылган жок"
        )

    return category_db


@category_router.put("/{category_id}/", response_model=TourCategoryOutSchema)
def update_category(
    category_id: int,
    category: TourCategoryUpdateSchema,
    db: Session = Depends(get_db)
):
    category_db = db.get(TourCategory, category_id)

    if category_db is None:
        raise HTTPException(
            status_code=404,
            detail="Категория табылган жок"
        )

    for key, value in category.model_dump(exclude_unset=True).items():
        setattr(category_db, key, value)

    db.commit()
    db.refresh(category_db)

    return category_db


@category_router.delete("/{category_id}/")
def delete_category(
    category_id: int,
    db: Session = Depends(get_db)
):
    category_db = db.get(TourCategory, category_id)

    if category_db is None:
        raise HTTPException(
            status_code=404,
            detail="Категория табылган жок"
        )

    if category_db.tours:
        raise HTTPException(
            status_code=400,
            detail="Бул категорияга турлар байланышкан"
        )

    db.delete(category_db)
    db.commit()

    return {"message": "Категория өчүрүлдү"}
