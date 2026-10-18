
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from mysite.database.db import get_db
from mysite.database.models import Region
from mysite.database.schema import (
    RegionInputSchema,
    RegionUpdateSchema,
    RegionOutSchema
)


region_router = APIRouter(
    prefix="/regions",
    tags=["Regions"]
)


def region_result(region_db):
    return {
        "id": region_db.id,
        "name": region_db.name,
        "image": region_db.image
    }


@region_router.post("/", response_model=RegionOutSchema)
def create_region(
    region: RegionInputSchema,
    db: Session = Depends(get_db)
):
    region_db = Region(
        name=region.name,
        image=region.image
    )

    db.add(region_db)
    db.commit()
    db.refresh(region_db)

    return region_result(region_db)


@region_router.get("/", response_model=list[RegionOutSchema])
def list_regions(
    db: Session = Depends(get_db)
):
    regions = db.query(Region).all()

    return [region_result(region) for region in regions]


@region_router.get("/{region_id}/", response_model=RegionOutSchema)
def detail_region(
    region_id: int,
    db: Session = Depends(get_db)
):
    region_db = db.get(Region, region_id)

    if region_db is None:
        raise HTTPException(
            status_code=404,
            detail="Область табылган жок"
        )

    return region_result(region_db)


@region_router.put("/{region_id}/", response_model=RegionOutSchema)
def update_region(
    region_id: int,
    region: RegionUpdateSchema,
    db: Session = Depends(get_db)
):
    region_db = db.get(Region, region_id)

    if region_db is None:
        raise HTTPException(
            status_code=404,
            detail="Область табылган жок"
        )

    data = region.model_dump(exclude_unset=True)

    if "name" in data:
        if data["name"] is None:
            raise HTTPException(
                status_code=400,
                detail="Область аты бош болбошу керек"
            )

        region_db.name = data["name"]

    if "image" in data:
        region_db.image = data["image"]

    db.commit()
    db.refresh(region_db)

    return region_result(region_db)


@region_router.delete("/{region_id}/")
def delete_region(
    region_id: int,
    db: Session = Depends(get_db)
):
    region_db = db.get(Region, region_id)

    if region_db is None:
        raise HTTPException(
            status_code=404,
            detail="Область табылган жок"
        )

    if region_db.districts or region_db.hotels:
        raise HTTPException(
            status_code=400,
            detail="Бул областька райондор же мейманканалар байланышкан"
        )

    db.delete(region_db)
    db.commit()

    return {"message": "Область өчүрүлдү"}
