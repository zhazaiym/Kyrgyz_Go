from fastapi import APIRouter, Depends, HTTPException
from fastapi_filter import FilterDepends
from sqlalchemy.orm import Session

from mysite.api.admin import require_admin_roles
from mysite.api.errors import error_detail
from mysite.api.filter_utils import Pagination, filtered_list
from mysite.database.db import get_db
from mysite.database.models import District, Region
from mysite.database.schemas.catalogue import (DistrictInputSchema, DistrictOutSchema,
                                               DistrictUpdateSchema)
from mysite.filters.filter import DistrictFilter
from mysite.translations.content import Language, localized, update_translations

district_router = APIRouter(prefix='/districts', tags=['Districts'])


@district_router.post(
    '/',
    response_model=DistrictOutSchema,
    dependencies=[Depends(require_admin_roles('catalog_editor'))],
)
def create_district(district: DistrictInputSchema, db: Session = Depends(get_db)):
    region_db = db.get(Region, district.region_id)

    if region_db is None:
        raise HTTPException(status_code=404, detail=error_detail('not_found'))

    district_db = District(**district.model_dump())

    db.add(district_db)
    update_translations(district_db)
    db.commit()
    db.refresh(district_db)

    return district_db


@district_router.get('/{district_id}/', response_model=DistrictOutSchema)
def detail_district(district_id: int, lang: Language = 'ru', db: Session = Depends(get_db)):
    district_db = db.get(District, district_id)

    if district_db is None:
        raise HTTPException(status_code=404, detail=error_detail('not_found'))

    return localized(district_db, lang)


@district_router.put(
    '/{district_id}/',
    response_model=DistrictOutSchema,
    dependencies=[Depends(require_admin_roles('catalog_editor'))],
)
def update_district(
    district_id: int, district: DistrictUpdateSchema, db: Session = Depends(get_db)
):
    district_db = db.get(District, district_id)

    if district_db is None:
        raise HTTPException(status_code=404, detail=error_detail('not_found'))

    data = district.model_dump(exclude_unset=True)

    if 'region_id' in data:
        if data['region_id'] is None:
            raise HTTPException(status_code=400, detail=error_detail('invalid_request'))

        region_db = db.get(Region, data['region_id'])

        if region_db is None:
            raise HTTPException(status_code=404, detail=error_detail('not_found'))

        if data['region_id'] != district_db.region_id and district_db.hotels:
            raise HTTPException(status_code=400, detail=error_detail('invalid_request'))

    for key, value in data.items():
        if key == 'name' and value is None:
            raise HTTPException(status_code=400, detail=error_detail('invalid_request'))

        setattr(district_db, key, value)

    update_translations(district_db)
    db.commit()
    db.refresh(district_db)

    return district_db


@district_router.delete(
    '/{district_id}/', dependencies=[Depends(require_admin_roles('catalog_editor'))]
)
def delete_district(district_id: int, db: Session = Depends(get_db)):
    district_db = db.get(District, district_id)

    if district_db is None:
        raise HTTPException(status_code=404, detail=error_detail('not_found'))

    if district_db.hotels:
        raise HTTPException(status_code=400, detail=error_detail('invalid_request'))

    db.delete(district_db)
    db.commit()

    return {'message': 'Район өчүрүлдү'}


@district_router.get('/', response_model=list[DistrictOutSchema])
def list_districts(
    lang: Language = 'ru',
    filters: DistrictFilter = FilterDepends(DistrictFilter),
    pagination: Pagination = Depends(),
    db: Session = Depends(get_db),
):
    districts = filtered_list(
        db=db, model=District, filters=filters, pagination=pagination, lang=lang
    )

    return [localized(district, lang) for district in districts]
