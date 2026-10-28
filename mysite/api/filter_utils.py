from fastapi import Query
from sqlalchemy import String, case, cast, func, or_, select
from sqlalchemy.orm import selectinload

from mysite.database.models import Tour, TourTranslation
from mysite.translations.content import CONTENT_FIELDS
from mysite.translations.source import TOUR_TRANSLATION_FIELDS


def _source_hash_expression(column):
    source_text = func.coalesce(cast(column, String), '')
    normalized = func.replace(func.replace(source_text, '\r\n', '\n'), '\r', '\n')
    return func.md5(normalized)


def _has_non_whitespace(expression):
    return func.regexp_replace(func.coalesce(expression, ''), '[[:space:]]', '', 'g') != ''


class Pagination:
    def __init__(
        self, limit: int = Query(100, ge=1, le=100), offset: int = Query(0, ge=0, le=1_000_000)
    ):
        self.limit = limit
        self.offset = offset


def _display_field(model, field, lang):
    original = getattr(model, field)
    if lang == 'ru':
        return original
    if model is Tour:
        if field not in TOUR_TRANSLATION_FIELDS:
            return original
        translated = (
            select(getattr(TourTranslation, field))
            .where(TourTranslation.tour_id == Tour.id, TourTranslation.lang == lang)
            .correlate(Tour)
            .scalar_subquery()
        )
        translated_hash = (
            select(TourTranslation.source_hashes[field].as_string())
            .where(TourTranslation.tour_id == Tour.id, TourTranslation.lang == lang)
            .correlate(Tour)
            .scalar_subquery()
        )
        return case(
            (
                (translated_hash == _source_hash_expression(original))
                & _has_non_whitespace(translated)
                & (original.isnot(None))
                & (original != ''),
                translated,
            ),
            else_=original,
        )
    if field not in CONTENT_FIELDS.get(model.__tablename__, ()):
        return original
    # JSON fields must follow the same non-empty-string fallback as localized().
    translated = model.translations[lang][field]
    hashes = model.translations[lang]['_source_hashes'][field].as_string()
    return case(
        (
            (func.json_typeof(translated) == 'string')
            & _has_non_whitespace(translated.as_string())
            & (hashes == _source_hash_expression(original))
            & (original.isnot(None))
            & (original != ''),
            translated.as_string(),
        ),
        else_=original,
    )


def filtered_list(db, model, filters, pagination, active_only=False, lang='ru'):
    query = db.query(model)
    if model is Tour and lang != 'ru':
        query = query.options(selectinload(Tour.translations))

    if active_only:
        query = query.filter(model.is_active.is_(True))

    # Search and sort use the displayed language, before pagination.
    search = getattr(filters, 'search', None)
    standard = filters.model_copy(update={'search': None, 'order_by': None})
    query = standard.filter(query)
    if search:
        # Treat wildcard characters as user text, not arbitrary SQL patterns.
        escaped = search.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        fields = filters.Constants.search_model_fields
        query = query.filter(
            or_(
                *[
                    _display_field(model, field, lang).ilike(f'%{escaped}%', escape='\\')
                    for field in fields
                ]
            )
        )
    for item in getattr(filters, 'order_by', None) or []:
        expression = _display_field(model, item.lstrip('+-'), lang)
        query = query.order_by(expression.desc() if item.startswith('-') else expression.asc())
    query = query.order_by(model.id.asc())

    return query.offset(pagination.offset).limit(pagination.limit).all()
