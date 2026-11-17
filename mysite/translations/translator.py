"""Catalogue translations; the model call itself lives in ML.translation."""

from ML.translation import translate_fields
from mysite.translations.source import TOUR_TRANSLATION_FIELDS

__all__ = ['translate_fields', 'translate_tour']


def translate_tour(data: dict):
    return translate_fields({field: data.get(field) for field in TOUR_TRANSLATION_FIELDS})
