from fastapi import Query
from sqlalchemy import String, case, cast, func, or_, select

from mysite.database.models import Tour, TourTranslation
from mysite.translations.content import CONTENT_FIELDS
from mysite.translations.source import TOUR_TRANSLATION_FIELDS


def _source_hash_expression(column):
    source_text = func.coalesce(cast(column, String), '')
    normalized = func.replace(func.replace(source_text, '\r\n', '\n'), '\r', '\n')
    return func.md5(normalized)


def _has_non_whitespace(expression):
    # Набор пробельных символов Python str.strip().
    whitespace = (
        '\t\n\v\f\r\x1c\x1d\x1e\x1f \x85\xa0\u1680'
        '\u2000\u2001\u2002\u2003\u2004\u2005\u2006'
        '\u2007\u2008\u2009\u200a\u2028\u2029\u202f'
        '\u205f\u3000'
    )
    return func.length(func.btrim(func.coalesce(expression, ''), whitespace)) > 0


class Pagination:
    def __init__(
        self, limit: int = Query(100, ge=1, le=100), offset: int = Query(0, ge=0, le=1_000_000)
    ):
        self.limit = limit
        self.offset = offset


def _display_field(model, field, lang, tour_translation=None):
    original = getattr(model, field)

    if lang == 'ru':
        return original

    if model is Tour:
        if field not in TOUR_TRANSLATION_FIELDS:
            return original

        if tour_translation is not None:
            translated = getattr(tour_translation, field)
            translated_hash = tour_translation.source_hashes[field].as_string()
        else:
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
                & original.is_not(None)
                & (original != ''),
                translated,
            ),
            else_=original,
        )

    if field not in CONTENT_FIELDS.get(model.__tablename__, ()):
        return original

    translated = model.translations[lang][field]
    translated_hash = model.translations[lang]['_source_hashes'][field].as_string()

    return case(
        (
            (func.json_typeof(translated) == 'string')
            & _has_non_whitespace(translated.as_string())
            & (translated_hash == _source_hash_expression(original))
            & original.is_not(None)
            & (original != ''),
            translated.as_string(),
        ),
        else_=original,
    )


def filtered_list(db, model, filters, pagination, active_only=False, lang='ru'):
    query = db.query(model)

    if active_only:
        query = query.filter(model.is_active.is_(True))
    if filters is not None:
        search_field = getattr(filters.Constants, 'search_field_name', 'search')
        ordering_field = getattr(filters.Constants, 'ordering_field_name', 'order_by')

        search = getattr(filters, search_field, None)
        ordering = getattr(filters, ordering_field, None)

        # Обычные фильтры применяем один раз.
        # Поиск и сортировку ниже выполняем по отображаемому языку.
        excluded_fields = {
            name: None
            for name in (search_field, ordering_field)
            if name in type(filters).model_fields
        }
        standard = filters.model_copy(update=excluded_fields)
        query = standard.filter(query)

        if search:
            escaped = search.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')

            fields = filters.Constants.search_model_fields
            expressions = [
                _display_field(model, field, lang).ilike(f'%{escaped}%', escape='\\')
                for field in fields
            ]

            if expressions:
                query = query.filter(or_(*expressions))

        for item in ordering or []:
            field = item.lstrip('+-')
            expression = _display_field(model, field, lang)

            query = query.order_by(expression.desc() if item.startswith('-') else expression.asc())

    # Стабильная пагинация при одинаковых значениях сортировки.
    query = query.order_by(model.id.asc())

    return query.offset(pagination.offset).limit(pagination.limit).all()
