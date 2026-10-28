import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi_filter import FilterDepends
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from mysite.api.admin import get_current_admin
from mysite.api.client_auth import current_client
from mysite.api.deletion_guards import protect_selected_item
from mysite.api.filter_utils import Pagination, filtered_list
from mysite.database.catalogue_schema import TourCardSchema
from mysite.database.db import get_db
from mysite.database.models import Country, Tour, TourCategory, TourTranslation
from mysite.database.schema import (
    TourDetailSchema,
    TourInputSchema,
    TourOutSchema,
    TourUpdateSchema,
)
from mysite.filters.filter import TourFilter
from mysite.translations.content import localized
from mysite.translations.jobs import schedule_translation, translate_record
from mysite.translations.translator import translate_tour

tour_router = APIRouter(prefix='/tours', tags=['Tours'])

logger = logging.getLogger(__name__)

LANGUAGES = ['en', 'de', 'zh']
TRANSLATED_FIELDS = ['title', 'description', 'included', 'excluded']


def try_save_translations(tour_db: Tour, db: Session):
    return schedule_translation(tour_db, TRANSLATED_FIELDS, translate_tour)


def get_localized_tour(
    tour_db: Tour, db: Session, lang: str, detail: bool = False, include_description: bool = False
):
    schema = (
        TourDetailSchema if detail else TourOutSchema if include_description else TourCardSchema
    )

    result = schema.model_validate(tour_db).model_dump(mode='json')

    if detail:
        result['programs'] = [localized(program, lang) for program in tour_db.programs]

    if lang == 'ru':
        return result

    translation_db = next((row for row in tour_db.translations if row.lang == lang), None)

    if translation_db is not None:
        for field in TRANSLATED_FIELDS if detail or include_description else ('title',):
            value = getattr(translation_db, field)
            if isinstance(value, str) and value:
                result[field] = value

    return result


@tour_router.post('/', response_model=TourOutSchema, dependencies=[Depends(get_current_admin)])
def create_tour(tour: TourInputSchema, db: Session = Depends(get_db)):
    if tour.country_id is not None and db.get(Country, tour.country_id) is None:
        raise HTTPException(404, 'Country not found')
    if tour.category_id is not None:
        category_db = db.get(TourCategory, tour.category_id)

        if category_db is None:
            raise HTTPException(status_code=404, detail='Категория табылган жок')

    try:
        tour_db = Tour(**tour.model_dump())

        db.add(tour_db)
        db.flush()

        try_save_translations(tour_db, db)

        db.commit()
        db.refresh(tour_db)

        return tour_db

    except SQLAlchemyError:
        db.rollback()
        logger.exception('Турду сактоо катасы')

        raise HTTPException(status_code=500, detail='Турду сактоо ишке ашкан жок')


@tour_router.get('/', response_model=list[TourCardSchema])
def list_tours(
    lang: str = Query(default='ru', pattern='^(ru|en|de|zh)$'),
    db: Session = Depends(get_db),
    filters: TourFilter = FilterDepends(TourFilter),
    pagination: Pagination = Depends(),
):
    tours = filtered_list(db, Tour, filters, pagination, active_only=True, lang=lang)

    return [get_localized_tour(tour, db, lang) for tour in tours]


@tour_router.get(
    '/{tour_id}/', response_model=TourDetailSchema, dependencies=[Depends(current_client)]
)
def detail_tour(
    tour_id: int,
    lang: str = Query(default='ru', pattern='^(ru|en|de|zh)$'),
    db: Session = Depends(get_db),
):
    tour_db = db.scalars(
        select(Tour)
        .options(
            selectinload(Tour.images), selectinload(Tour.programs), selectinload(Tour.translations)
        )
        .where(Tour.id == tour_id)
    ).first()

    if tour_db is None or not tour_db.is_active:
        raise HTTPException(status_code=404, detail='Тур табылган жок')

    return get_localized_tour(tour_db, db, lang, detail=True)


@tour_router.put(
    '/{tour_id}/', response_model=TourOutSchema, dependencies=[Depends(get_current_admin)]
)
def update_tour(tour_id: int, tour: TourUpdateSchema, db: Session = Depends(get_db)):
    tour_db = db.scalars(select(Tour).where(Tour.id == tour_id)).first()

    if tour_db is None:
        raise HTTPException(status_code=404, detail='Тур табылган жок')

    data = tour.model_dump(exclude_unset=True)
    if data.get('country_id') is not None and db.get(Country, data['country_id']) is None:
        raise HTTPException(404, 'Country not found')
    minimum = data.get('min_people', tour_db.min_people)
    maximum = data.get('max_people', tour_db.max_people)
    if maximum is not None and minimum > maximum:
        raise HTTPException(422, 'min_people cannot exceed max_people')

    if data.get('category_id') is not None:
        category_db = db.get(TourCategory, data['category_id'])

        if category_db is None:
            raise HTTPException(status_code=404, detail='Категория табылган жок')

    try:
        for key, value in data.items():
            setattr(tour_db, key, value)

        db.flush()

        if any(field in data for field in TRANSLATED_FIELDS):
            db.query(TourTranslation).filter(TourTranslation.tour_id == tour_db.id).delete(
                synchronize_session=False
            )
            db.flush()
            try_save_translations(tour_db, db)

        db.commit()
        db.refresh(tour_db)

        return tour_db

    except SQLAlchemyError:
        db.rollback()
        logger.exception('Турду жаңыртуу катасы')

        raise HTTPException(status_code=500, detail='Турду жаңыртуу ишке ашкан жок')


@tour_router.post('/{tour_id}/translate/', dependencies=[Depends(get_current_admin)])
def retry_tour_translation(tour_id: int, db: Session = Depends(get_db)):
    tour_db = db.scalars(select(Tour).where(Tour.id == tour_id)).first()

    if tour_db is None:
        raise HTTPException(status_code=404, detail='Тур табылган жок')

    try:
        source = {field: getattr(tour_db, field) for field in TRANSLATED_FIELDS}
        db.commit()
        result = translate_record(Tour, tour_id, source, translate_tour)
        if result == 'busy':
            raise HTTPException(
                status_code=503, detail='Котормо кезеги бош эмес, кайра аракет кылыңыз'
            )
        if result == 'source_changed':
            raise HTTPException(status_code=409, detail='Тур өзгөрдү; котормону кайра сураңыз')
        if result == 'missing':
            raise HTTPException(status_code=404, detail='Тур табылган жок')
        if result != 'translated':
            raise HTTPException(status_code=502, detail='Gemini котормосу азыр жеткиликсиз')

        db.commit()

        return {'message': 'Тур 3 тилге которулду', 'languages': LANGUAGES}

    except HTTPException:
        raise

    except SQLAlchemyError:
        db.rollback()
        logger.exception('Котормону сактоо катасы')

        raise HTTPException(status_code=500, detail='Котормону сактоо ишке ашкан жок')


@tour_router.delete('/{tour_id}/', dependencies=[Depends(get_current_admin)])
def delete_tour(tour_id: int, db: Session = Depends(get_db)):
    tour_db = db.get(Tour, tour_id)

    if tour_db is None:
        raise HTTPException(status_code=404, detail='Тур табылган жок')

    protect_selected_item(db, Tour, tour_id)

    try:
        db.query(TourTranslation).filter(TourTranslation.tour_id == tour_id).delete(
            synchronize_session=False
        )

        db.delete(tour_db)
        db.commit()

        return {'message': 'Тур өчүрүлдү'}

    except SQLAlchemyError:
        db.rollback()
        logger.exception('Турду өчүрүү катасы')

        raise HTTPException(status_code=500, detail='Турду өчүрүү ишке ашкан жок')


@tour_router.get('/home/slides/')
def home_tour_slides(
    lang: str = Query(default='ru', pattern='^(ru|en|de|zh)$'),
    db: Session = Depends(get_db),
    pagination: Pagination = Depends(),
):
    tours = db.scalars(
        select(Tour)
        .options(selectinload(Tour.translations))
        .where(Tour.is_active.is_(True), Tour.main_image.isnot(None), Tour.main_image != '')
        .order_by(Tour.id.asc())
        .offset(pagination.offset)
        .limit(pagination.limit)
    ).all()

    slides = []

    for tour in tours:
        data = get_localized_tour(tour, db, lang, include_description=True)

        slides.append(
            {
                'id': tour.id,
                'title': data['title'],
                'description': data['description'],
                'image': tour.main_image,
            }
        )

    return {'total': len(slides), 'slides': slides}


@tour_router.get('/category/{category_id}/', response_model=list[TourCardSchema])
def tours_by_category(
    category_id: int,
    lang: str = Query(default='ru', pattern='^(ru|en|de|zh)$'),
    db: Session = Depends(get_db),
    pagination: Pagination = Depends(),
):
    category_db = db.get(TourCategory, category_id)

    if category_db is None:
        raise HTTPException(status_code=404, detail='Категория табылган жок')

    tours = db.scalars(
        select(Tour)
        .options(selectinload(Tour.translations))
        .where(Tour.category_id == category_id, Tour.is_active.is_(True))
        .order_by(Tour.id)
        .offset(pagination.offset)
        .limit(pagination.limit)
    ).all()

    return [get_localized_tour(tour, db, lang) for tour in tours]
