from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from mysite.database.db import get_db
from mysite.api.admin import get_current_admin
from mysite.translations.content import Language, localized, update_translations
from mysite.database.models import Region, Country
from mysite.database.schema import (
    RegionInputSchema,
    RegionUpdateSchema,
    RegionOutSchema
)

from fastapi_filter import FilterDepends

from mysite.filters.filter import RegionFilter
from mysite.api.filter_utils import Pagination, filtered_list

region_router = APIRouter(
    prefix="/regions",
    tags=["Regions"]
)


def region_result(region_db):
    return {
        "id": region_db.id,
        "name": region_db.name,
        "image": region_db.image,
        "country_id": region_db.country_id
    }


@region_router.post("/", response_model=RegionOutSchema, dependencies=[Depends(get_current_admin)])
def create_region(
    region: RegionInputSchema,
    db: Session = Depends(get_db)
):
    if region.country_id is not None:
        country_db = db.get(Country, region.country_id)

        if country_db is None:
            raise HTTPException(
                status_code=404,
                detail="Мындай мамлекет жок"
            )

    region_db = Region(
        name=region.name,
        image=region.image,
        country_id=region.country_id
    )

    db.add(region_db)
    update_translations(region_db)
    db.commit()
    db.refresh(region_db)

    return region_result(region_db)


@region_router.get("/", response_model=list[RegionOutSchema])
def list_regions(
    lang: Language = "ru",
    db: Session = Depends(get_db)
):
    regions = db.query(Region).all()

    return [localized(record, lang) for record in regions]


@region_router.get("/{region_id}/", response_model=RegionOutSchema)
def detail_region(
    region_id: int,
    lang: Language = "ru",
    db: Session = Depends(get_db)
):
    region_db = db.get(Region, region_id)

    if region_db is None:
        raise HTTPException(
            status_code=404,
            detail="Область табылган жок"
        )

    return localized(region_db, lang)


@region_router.put("/{region_id}/", response_model=RegionOutSchema, dependencies=[Depends(get_current_admin)])
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

    if "country_id" in data:
        if data["country_id"] is not None:
            country_db = db.get(
                Country,
                data["country_id"]
            )

            if country_db is None:
                raise HTTPException(
                    status_code=404,
                    detail="Мындай мамлекет жок"
                )

        region_db.country_id = data["country_id"]

    update_translations(region_db)
    db.commit()
    db.refresh(region_db)

    return region_result(region_db)


@region_router.delete("/{region_id}/", dependencies=[Depends(get_current_admin)])
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


@region_router.get("/", response_model=list[RegionOutSchema])
def list_regions(
    lang: Language = "ru",
    filters: RegionFilter = FilterDepends(RegionFilter),
    pagination: Pagination = Depends(),
    db: Session = Depends(get_db),
):
    regions = filtered_list(
        db=db,
        model=Region,
        filters=filters,
        pagination=pagination,
    )

    return [localized(region, lang) for region in regions]

