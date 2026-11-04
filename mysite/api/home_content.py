"""Public homepage copy served to the frontend."""

from fastapi import APIRouter, Query

home_content_router = APIRouter(prefix='/home', tags=['Home'])

_HOME_CONTENT = {
    'ru': {
        'title': 'Мы создаём путешествия, которые объединяют мир.',
        'description': (
            'Kerben Travels — команда профессионалов, влюблённых в путешествия. '
            'Организуем туры по Центральной Азии и всему миру, а также принимаем '
            'гостей в Кыргызстане.'
        ),
        'details': (
            'От первого обращения до возвращения домой мы продумываем каждую деталь: '
            'трансферы, проживание, питание и экскурсии.'
        ),
        'promise': 'Вы наслаждаетесь путешествием — обо всём остальном заботимся мы.',
    },
    'en': {
        'title': 'We create journeys that bring the world together.',
        'description': (
            'Kerben Travels is a team of travel professionals. We organize tours '
            'across Central Asia and around the world, and welcome guests to Kyrgyzstan.'
        ),
        'details': (
            'From your first inquiry until you return home, we plan every detail: '
            'transfers, accommodation, meals, and excursions.'
        ),
        'promise': 'Enjoy the journey — we take care of everything else.',
    },
    'de': {
        'title': 'Wir schaffen Reisen, die die Welt verbinden.',
        'description': (
            'Kerben Travels ist ein Team von Reiseprofis. Wir organisieren Reisen '
            'durch Zentralasien und die ganze Welt und heißen Gäste in Kirgisistan willkommen.'
        ),
        'details': (
            'Von der ersten Anfrage bis zu Ihrer Rückkehr planen wir jedes Detail: '
            'Transfers, Unterkunft, Verpflegung und Ausflüge.'
        ),
        'promise': 'Genießen Sie Ihre Reise — um alles andere kümmern wir uns.',
    },
    'zh': {
        'title': '我们打造连接世界的旅程。',
        'description': (
            'Kerben Travels 是一支热爱旅行的专业团队。我们组织中亚及世界各地的旅行，'
            '也在吉尔吉斯斯坦接待宾客。'
        ),
        'details': '从首次咨询到您平安返家，我们都会妥善安排每个细节：接送、住宿、餐饮和游览。',
        'promise': '尽情享受旅程，其余的一切交给我们。',
    },
}


@home_content_router.get('/content/')
def get_home_content(lang: str = Query(default='ru', pattern='^(ru|en|de|zh)$')):
    """Return localized homepage copy for the requested supported language."""
    return {'lang': lang, **_HOME_CONTENT[lang]}
