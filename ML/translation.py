import json

from langchain_core.messages import HumanMessage, SystemMessage

from ML.errors import PROVIDER_ERRORS, AIError, classify_error
from ML.provider import LazyClient

# Answers in the Translations schema instead of free text.
translator = LazyClient('translator')

TARGET_LANGUAGES = ('en', 'de', 'zh')


def translate_fields(source: dict):
    if not any(source.values()):
        return {}
    try:
        return _translate_fields(source)
    except PROVIDER_ERRORS as exc:
        raise classify_error(exc) from None
    except (ValueError, TypeError):
        raise AIError('ai_invalid_response') from None


def _translate_fields(source):
    try:
        response = translator.invoke(
            [
                SystemMessage(
                    content=(
                        'Translate the provided Russian tourism fields into English (en), '
                        'German (de), and Simplified Chinese (zh). Preserve names and numbers. '
                        'For each language return every supplied field once, with its name '
                        'unchanged in "field" and the translation in "text".'
                    )
                ),
                HumanMessage(
                    content=json.dumps(
                        {field: value for field, value in source.items() if value},
                        ensure_ascii=False,
                    )
                ),
            ]
        )
    except (ValueError, TypeError):
        raise AIError('ai_unavailable') from None

    raw = response.get('raw')
    reason = (
        str(getattr(raw, 'response_metadata', {}).get('finish_reason', ''))
        .upper()
        .rsplit('.', 1)[-1]
    )
    if reason in {'SAFETY', 'RECITATION', 'BLOCKLIST', 'PROHIBITED_CONTENT', 'SPII'}:
        raise AIError('ai_blocked')
    parsed = response.get('parsed')
    if reason not in {'', 'STOP'} or parsed is None:
        raise AIError('ai_invalid_response')
    result = {}
    for lang in TARGET_LANGUAGES:
        translated = {item.field: item.text for item in getattr(parsed, lang)}
        result[lang] = {}
        for field, original in source.items():
            value = original if original is None or original == '' else translated.get(field)
            if value is not original and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f'Invalid translation: {lang}.{field}')
            result[lang][field] = value
    return result
