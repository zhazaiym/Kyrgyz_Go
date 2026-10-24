
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

model = ChatGoogleGenerativeAI(
    model=os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"),
    google_api_key=GEMINI_API_KEY,
    temperature=0.3
)
# model = ChatGoogleGenerativeAI(
#     model=os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"),
#     temperature=0,
#     max_retries=int(os.getenv("GEMINI_MAX_RETRIES", "1")),
# )

LANGUAGES = {
    "ru": "Russian",
    "en": "English",
    "de": "German",
    "zh": "Simplified Chinese"
}

FIELDS = ["title", "description", "included", "excluded"]


def translate_text(text: str, lang: str):
    if lang not in LANGUAGES:
        raise ValueError("Мындай тил жок")

    if lang == "ru" or not text:
        return text

    messages = [
        SystemMessage(
            content=(
                f"Translate this Russian tourism text into "
                f"{LANGUAGES[lang]}. "
                "Preserve place names, numbers and meaning. "
                "Return only translated text."
            )
        ),
        HumanMessage(content=text)
    ]

    response = model.invoke(messages)

    return str(response.content)


def translate_fields(source: dict):
    if not any(source.values()):
        return {}
    response = model.invoke([
        SystemMessage(content=(
            'Translate the provided Russian tourism fields into English (en), '
            'German (de), and Simplified Chinese (zh). Preserve names and numbers. '
            'Return only a JSON object keyed by en, de, zh, each containing '
            'exactly the supplied field names. Keep null and empty values unchanged.'
        )),
        HumanMessage(content=json.dumps(source, ensure_ascii=False)),
    ])
    content = str(response.content).strip()
    if content.startswith('```'):
        content = content.split('\n', 1)[1].rsplit('```', 1)[0].strip()
    result = json.loads(content)
    for lang in ('en', 'de', 'zh'):
        for field, original in source.items():
            value = result[lang][field]
            if original is None or original == '':
                result[lang][field] = original
            elif not isinstance(value, str) or not value.strip():
                raise ValueError(f'Invalid translation: {lang}.{field}')
    return result


def translate_tour(data: dict):
    source = {
        field: data.get(field)
        for field in FIELDS
    }

    messages = [
        SystemMessage(
            content=(
                "You are a professional tourism translator. "
                "Translate all provided Russian tourism fields "
                "into English (en), German (de), and "
                "Simplified Chinese (zh). "
                "Preserve names, numbers and meaning. "
                "Keep null values as null. "
                "Return ONLY valid JSON without markdown. "
                "Use exactly this structure: "
                '{"en":{"title":"","description":"","included":"","excluded":""},'
                '"de":{"title":"","description":"","included":"","excluded":""},'
                '"zh":{"title":"","description":"","included":"","excluded":""}}'
            )
        ),
        HumanMessage(
            content=json.dumps(source, ensure_ascii=False)
        )
    ]

    response = model.invoke(messages)

    content = str(response.content).strip()

    if content.startswith("```"):
        content = content.split("\n", 1)[1]
        content = content.rsplit("```", 1)[0].strip()

    translations = json.loads(content)

    for lang in ["en", "de", "zh"]:
        if lang not in translations:
            raise ValueError(f"{lang} котормосу жок")

        for field in FIELDS:
            if field not in translations[lang]:
                raise ValueError(
                    f"{lang}: {field} талаасы жок"
                )

            if source[field] is None:
                translations[lang][field] = None
            elif not isinstance(translations[lang][field], str):
                raise ValueError(
                    f"{lang}: {field} туура эмес"
                )

    return translations
