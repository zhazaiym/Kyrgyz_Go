import json

from langchain_core.messages import HumanMessage, SystemMessage

from ML.context import text_content
from ML.errors import PROVIDER_ERRORS, AIError, classify_error
from ML.provider import LazyClient
from mysite.translations.source import TOUR_TRANSLATION_FIELDS

model = LazyClient('translation')

LANGUAGES = {'ru': 'Russian', 'en': 'English', 'de': 'German', 'zh': 'Simplified Chinese'}

FIELDS = TOUR_TRANSLATION_FIELDS


def translate_fields(source: dict):
    if not any(source.values()):
        return {}
    try:
        return _translate_fields(source)
    except PROVIDER_ERRORS as exc:
        raise classify_error(exc) from None


def _translate_fields(source):
    response = model.invoke(
        [
            SystemMessage(
                content=(
                    'Translate the provided Russian tourism fields into English (en), '
                    'German (de), and Simplified Chinese (zh). Preserve names and numbers. '
                    'Return only a JSON object keyed by en, de, zh, each containing '
                    'exactly the supplied field names. Keep null and empty values unchanged.'
                )
            ),
            HumanMessage(content=json.dumps(source, ensure_ascii=False)),
        ]
    )
    reason = (
        str(getattr(response, 'response_metadata', {}).get('finish_reason', ''))
        .upper()
        .rsplit('.', 1)[-1]
    )
    if reason in {'SAFETY', 'RECITATION', 'BLOCKLIST', 'PROHIBITED_CONTENT', 'SPII'}:
        raise AIError('ai_blocked')
    if reason not in {'', 'STOP'}:
        raise AIError('ai_invalid_response')
    content = text_content(response.content).strip()
    if len(content) > 65_536:
        raise AIError('ai_invalid_response')
    if content.startswith('```'):
        content = content.split('\n', 1)[1].rsplit('```', 1)[0].strip()
    result = json.loads(content)
    if not isinstance(result, dict):
        raise ValueError('Translation response must be a JSON object')
    result = {lang: result.get(lang) for lang in ('en', 'de', 'zh')}
    for lang in ('en', 'de', 'zh'):
        if not isinstance(result[lang], dict):
            raise ValueError(f'Missing translation language: {lang}')
        result[lang] = {field: result[lang].get(field) for field in source}
        for field, original in source.items():
            value = result[lang][field]
            if original is None or original == '':
                result[lang][field] = original
            elif not isinstance(value, str) or not value.strip():
                raise ValueError(f'Invalid translation: {lang}.{field}')
    return result


def translate_tour(data: dict):
    return translate_fields({field: data.get(field) for field in FIELDS})
