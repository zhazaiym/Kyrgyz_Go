from fastapi import Query
from sqlalchemy import String, and_, case, cast, func, or_
from sqlalchemy.orm import aliased, selectinload

from mysite.database.models import Tour, TourTranslation
from mysite.translations.content import CONTENT_FIELDS
from mysite.translations.source import TOUR_TRANSLATION_FIELDS


def _source_hash_expression(column):
    source_text = func.coalesce(cast(column, String), '')
    normalized = func.replace(func.replace(source_text, '\r\n', '\n'), '\r', '\n')
    return func.md5(normalized)


def _has_non_whitespace(expression):
    # Frozen Python str.strip() whitespace set, independent of PostgreSQL locale.
    whitespace = '\t\n\v\f\r\x1c\x1d\x1e\x1f \x85\xa0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000'
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
        if field not in TOUR_TRANSLATION_FIELDS or tour_translation is None:
            return original

        translated = getattr(tour_translation, field)
        translated_hash = tour_translation.source_hashes[field].as_string()

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
    hashes = model.translations[lang]['_source_hashes'][field].as_string()

    return case(
        (
            (func.json_typeof(translated) == 'string')
            & _has_non_whitespace(translated.as_string())
            & (hashes == _source_hash_expression(original))
            & original.is_not(None)
            & (original != ''),
            translated.as_string(),
        ),
        else_=original,
    )
def filtered_list(*, db, model, filters, pagination, lang='ru'):
    query = db.query(model)

    if filters is not None:
        query = filters.filter(query)

        ordering_field = filters.Constants.ordering_field_name
        ordering = getattr(filters, ordering_field, None)

        if ordering:
            query = filters.sort(query)

    # Stable ordering for pagination, including equal sort values.
    query = query.order_by(model.id.asc())

    return (
        query
        .offset(pagination.offset)
        .limit(pagination.limit)
        .all()
    )
