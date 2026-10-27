
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from mysite.database.db import get_db
from mysite.api.admin import get_current_admin
from mysite.translations.content import Language, localized, update_translations
from mysite.database.models import District, Region
from mysite.database.schema import (
    DistrictInputSchema,
    DistrictUpdateSchema,
    DistrictOutSchema
)

from fastapi_filter import FilterDepends

from mysite.filters.filter import DistrictFilter
from mysite.api.filter_utils import Pagination, filtered_list



district_router = APIRouter(
    prefix="/districts",
    tags=["Districts"]
)


@district_router.post("/", response_model=DistrictOutSchema, dependencies=[Depends(get_current_admin)])
def create_district(
    district: DistrictInputSchema,
    db: Session = Depends(get_db)
):
    region_db = db.get(Region, district.region_id)

    if region_db is None:
        raise HTTPException(
            status_code=404,
            detail="Область табылган жок"
        )

    district_db = District(**district.model_dump())

    db.add(district_db)
    update_translations(district_db)
    db.commit()
    db.refresh(district_db)

    return district_db


@district_router.get("/", response_model=list[DistrictOutSchema])
def list_districts(
    lang: Language = "ru",
    db: Session = Depends(get_db)
):
    return [localized(record, lang) for record in db.query(District).all()]


@district_router.get("/{district_id}/", response_model=DistrictOutSchema)
def detail_district(
    district_id: int,
    lang: Language = "ru",
    db: Session = Depends(get_db)
):
    district_db = db.get(District, district_id)

    if district_db is None:
        raise HTTPException(
            status_code=404,
            detail="Район табылган жок"
        )

    return localized(district_db, lang)


@district_router.put("/{district_id}/", response_model=DistrictOutSchema, dependencies=[Depends(get_current_admin)])
def update_district(
    district_id: int,
    district: DistrictUpdateSchema,
    db: Session = Depends(get_db)
):
    district_db = db.get(District, district_id)

    if district_db is None:
        raise HTTPException(
            status_code=404,
            detail="Район табылган жок"
        )

    data = district.model_dump(exclude_unset=True)

    if "region_id" in data:
        if data["region_id"] is None:
            raise HTTPException(
                status_code=400,
                detail="Область милдеттүү"
            )

        region_db = db.get(Region, data["region_id"])

        if region_db is None:
            raise HTTPException(
                status_code=404,
                detail="Область табылган жок"
            )

        if (
            data["region_id"] != district_db.region_id
            and district_db.hotels
        ):
            raise HTTPException(
                status_code=400,
                detail="Районго мейманканалар байланышкан"
            )

    for key, value in data.items():
        if key == "name" and value is None:
            raise HTTPException(
                status_code=400,
                detail="Райондун аты бош болбошу керек"
            )

        setattr(district_db, key, value)

    update_translations(district_db)
    db.commit()
    db.refresh(district_db)

    return district_db


@district_router.delete("/{district_id}/", dependencies=[Depends(get_current_admin)])
def delete_district(
    district_id: int,
    db: Session = Depends(get_db)
):
    district_db = db.get(District, district_id)

    if district_db is None:
        raise HTTPException(
            status_code=404,
            detail="Район табылган жок"
        )

    if district_db.hotels:
        raise HTTPException(
            status_code=400,
            detail="Бул районго мейманканалар байланышкан"
        )

    db.delete(district_db)
    db.commit()

    return {"message": "Район өчүрүлдү"}


@district_router.get("/", response_model=list[DistrictOutSchema])
def list_districts(
    lang: Language = "ru",
    filters: DistrictFilter = FilterDepends(DistrictFilter),
    pagination: Pagination = Depends(),
    db: Session = Depends(get_db),
):
    districts = filtered_list(
        db=db,
        model=District,
        filters=filters,
        pagination=pagination,
    )

    return [
        localized(district, lang)
        for district in districts
    ]
