import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi_filter import FilterDepends
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from mysite.api.errors import error_detail
from mysite.api.filter_utils import Pagination, filtered_list
from mysite.database.catalogue_schema import TourCardSchema
from mysite.database.db import get_db
from mysite.database.models import Tour, TourCategory
from mysite.database.schemas.catalogue import TourDetailSchema, TourOutSchema
from mysite.database.tour_review_models import TourReview
from mysite.filters.filter import TourFilter
from mysite.translations.content import localized
from mysite.translations.source import TOUR_TRANSLATION_FIELDS, translation_ready

tour_router = APIRouter(prefix='/tours', tags=['Tours'])

logger = logging.getLogger(__name__)

LANGUAGES = ['en', 'de', 'zh']
TRANSLATED_FIELDS = TOUR_TRANSLATION_FIELDS


def get_localized_tour(
    tour_db: Tour, lang: str, detail: bool = False, include_description: bool = False
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
                .filter(TourReview.tour_id.in_(tour_ids), TourReview.status == 'published')
                .group_by(TourReview.tour_id)
                .all()
            )
        }

    results = []
    for tour in tours:
        result = get_localized_tour(tour, lang)
        result['average_rating'], result['review_count'] = aggregates.get(tour.id, (None, 0))
        results.append(result)
    return results


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

    return get_localized_tour(tour_db, lang, detail=True)


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
        data = get_localized_tour(tour, lang, include_description=True)

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
