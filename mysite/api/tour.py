import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi_filter import FilterDepends
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from mysite.api.admin import require_admin_roles
from mysite.api.deletion_guards import protect_selected_item
from mysite.api.errors import error_detail
from mysite.api.filter_utils import Pagination, filtered_list
from mysite.database.catalogue_schema import TourCardSchema
from mysite.database.db import get_db
from mysite.database.models import Country, Tour, TourCategory, TourTranslation
from mysite.database.schemas.catalogue import (TourDetailSchema, TourInputSchema, TourOutSchema,
                                               TourUpdateSchema)
from mysite.database.tour_review_models import TourReview
from mysite.filters.filter import TourFilter
from mysite.translations.content import localized
from mysite.translations.jobs import schedule_translation, translate_record
from mysite.translations.source import (TOUR_TRANSLATION_FIELDS, active_manual_fields,
                                        normalize_text, source_value_changed, translation_ready)
from mysite.translations.translator import translate_tour

tour_router = APIRouter(prefix='/tours', tags=['Tours'])

logger = logging.getLogger(__name__)

LANGUAGES = ['en', 'de', 'zh']
TRANSLATED_FIELDS = TOUR_TRANSLATION_FIELDS


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
        source_hashes = translation_db.source_hashes or {}

        for field in TRANSLATED_FIELDS if detail or include_description else ('title',):
            value = getattr(translation_db, field)

            if getattr(tour_db, field) not in (None, '') and translation_ready(
                value, source_hashes.get(field), getattr(tour_db, field)
            ):
                result[field] = value

    return result


def localized_tour_cards_with_reviews(tours, db: Session, lang: str):
    tour_ids = [tour.id for tour in tours]
    aggregates = {}
    if tour_ids:
        aggregates = {
            tour_id: (round(float(average), 2), count)
            for tour_id, average, count in (
                db.query(TourReview.tour_id, func.avg(TourReview.rating), func.count(TourReview.id))
                .filter(TourReview.tour_id.in_(tour_ids))
                .group_by(TourReview.tour_id)
                .all()
            )
        }

    results = []
    for tour in tours:
        result = get_localized_tour(tour, db, lang)
        result['average_rating'], result['review_count'] = aggregates.get(tour.id, (None, 0))
        results.append(result)
    return results


@tour_router.post(
    '/', response_model=TourOutSchema, dependencies=[Depends(require_admin_roles('catalog_editor'))]
)
def create_tour(tour: TourInputSchema, db: Session = Depends(get_db)):
    if tour.country_id is not None and db.get(Country, tour.country_id) is None:
        raise HTTPException(404, error_detail('not_found'))
    if tour.category_id is not None:
        category_db = db.get(TourCategory, tour.category_id)

        if category_db is None:
            raise HTTPException(status_code=404, detail=error_detail('not_found'))

    try:
        tour_db = Tour(**tour.model_dump())

        db.add(tour_db)
        db.flush()

        schedule_translation(tour_db, TRANSLATED_FIELDS, translate_tour)

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
    return localized_tour_cards_with_reviews(tours, db, lang)


@tour_router.get('/{tour_id}/', response_model=TourDetailSchema)
def detail_tour(
    tour_id: int,
    lang: str = Query(default='ru', pattern='^(ru|en|de|zh)$'),
    db: Session = Depends(get_db),
):
    tour_db = db.scalars(
        select(Tour)
        .options(
            selectinload(Tour.videos),
            selectinload(Tour.images),
            selectinload(Tour.programs),
            selectinload(Tour.translations),
        )
        .where(Tour.id == tour_id)
    ).first()

    if tour_db is None or not tour_db.is_active:
        raise HTTPException(status_code=404, detail=error_detail('not_found'))

    return get_localized_tour(tour_db, db, lang, detail=True)


@tour_router.put(
    '/{tour_id}/',
    response_model=TourOutSchema,
    dependencies=[Depends(require_admin_roles('catalog_editor'))],
)
def update_tour(tour_id: int, tour: TourUpdateSchema, db: Session = Depends(get_db)):
    tour_db = db.scalars(select(Tour).where(Tour.id == tour_id)).first()

    if tour_db is None:
        raise HTTPException(status_code=404, detail=error_detail('not_found'))

    data = tour.model_dump(exclude_unset=True)
    data = {
        field: normalize_text(value) if field in TRANSLATED_FIELDS else value
        for field, value in data.items()
    }
    source_changed = any(
        field in data and source_value_changed(getattr(tour_db, field), data[field])
        for field in TRANSLATED_FIELDS
    )
    if data.get('country_id') is not None and db.get(Country, data['country_id']) is None:
        raise HTTPException(404, error_detail('not_found'))
    minimum = data.get('min_people', tour_db.min_people)
    maximum = data.get('max_people', tour_db.max_people)
    if maximum is not None and minimum > maximum:
        raise HTTPException(422, error_detail('validation_error'))

    if data.get('category_id') is not None:
        category_db = db.get(TourCategory, data['category_id'])

        if category_db is None:
            raise HTTPException(status_code=404, detail=error_detail('not_found'))

    try:
        for key, value in data.items():
            setattr(tour_db, key, value)

        if source_changed:
            source = {field: getattr(tour_db, field) for field in TRANSLATED_FIELDS}
            for translation in tour_db.translations:
                translation.source_hashes = translation.source_hashes or {}
                translation.manual_fields = active_manual_fields(
                    translation.manual_fields or [], translation.source_hashes, source
                )

        db.flush()

        if source_changed:
            schedule_translation(tour_db, TRANSLATED_FIELDS, translate_tour)

        db.commit()
        db.refresh(tour_db)

        return tour_db

    except SQLAlchemyError:
        db.rollback()
        logger.exception('Турду жаңыртуу катасы')

        raise HTTPException(status_code=500, detail='Турду жаңыртуу ишке ашкан жок')


@tour_router.post(
    '/{tour_id}/translate/', dependencies=[Depends(require_admin_roles('catalog_editor'))]
)
def retry_tour_translation(tour_id: int, db: Session = Depends(get_db)):
    tour_db = db.scalars(select(Tour).where(Tour.id == tour_id)).first()

    if tour_db is None:
        raise HTTPException(status_code=404, detail=error_detail('not_found'))

    try:
        source = {field: getattr(tour_db, field) for field in TRANSLATED_FIELDS}
        db.commit()
        result = translate_record(Tour, tour_id, source, translate_tour)
        if result == 'busy':
            raise HTTPException(status_code=503, detail=error_detail('service_unavailable'))
        if result == 'source_changed':
            raise HTTPException(status_code=409, detail=error_detail('conflict'))
        if result == 'missing':
            raise HTTPException(status_code=404, detail=error_detail('not_found'))
        if result != 'translated':
            raise HTTPException(status_code=502, detail=error_detail('service_unavailable'))

        db.commit()

        return {'message': 'Тур 3 тилге которулду', 'languages': LANGUAGES}

    except HTTPException:
        raise

    except SQLAlchemyError:
        db.rollback()
        logger.exception('Котормону сактоо катасы')

        raise HTTPException(status_code=500, detail='Котормону сактоо ишке ашкан жок')


@tour_router.delete('/{tour_id}/', dependencies=[Depends(require_admin_roles('catalog_editor'))])
def delete_tour(tour_id: int, db: Session = Depends(get_db)):
    tour_db = db.get(Tour, tour_id)

    if tour_db is None:
        raise HTTPException(status_code=404, detail=error_detail('not_found'))

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
        raise HTTPException(status_code=404, detail=error_detail('not_found'))

    tours = db.scalars(
        select(Tour)
        .options(selectinload(Tour.translations))
        .where(Tour.category_id == category_id, Tour.is_active.is_(True))
        .order_by(Tour.id)
        .offset(pagination.offset)
        .limit(pagination.limit)
    ).all()

    return localized_tour_cards_with_reviews(tours, db, lang)
