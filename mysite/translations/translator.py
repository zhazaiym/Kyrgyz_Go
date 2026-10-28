import json
import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from mysite.translations.source import TOUR_TRANSLATION_FIELDS

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / '.env')

GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

model = ChatGoogleGenerativeAI(
    model=os.getenv('GEMINI_MODEL', 'gemini-3.5-flash-lite'),
    google_api_key=GEMINI_API_KEY,
    temperature=0.3,
    timeout=15,
    max_retries=1,
)


def translate_fields(source: dict):
    if not any(source.values()):
        return {}
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
    content = str(response.content).strip()
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
    return translate_fields({field: data.get(field) for field in TOUR_TRANSLATION_FIELDS})
