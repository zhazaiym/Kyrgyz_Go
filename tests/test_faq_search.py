"""FAQ search table: four languages, inflected forms, typos and questions off the topic."""

import pytest

from ML import tools
from mysite.database.db import SessionLocal
from mysite.database.models import FAQ

VISA = 'Нужна ли виза для посещения Кыргызстана?'
INSURANCE = 'Нужна ли туристическая страховка?'
CARD = 'Можно ли расплачиваться банковской картой?'
FOOD = 'Можно ли организовать вегетарианское, веганское или халяльное питание?'
CHILDREN = 'Можно ли путешествовать по Кыргызстану с детьми?'
SIM = 'Можно ли приобрести местную SIM-карту?'

# The migration stores Russian and English; German and Chinese come from the translation jobs.
GENERATED = {
    VISA: {
        'de': {
            'question': 'Brauche ich ein Visum für Kirgisistan?',
            'answer': 'Die Visumpflicht hängt von Ihrer Staatsangehörigkeit ab.',
        },
        'zh': {'question': '去吉尔吉斯斯坦需要签证吗？', 'answer': '签证要求取决于您的国籍。'},
    },
    INSURANCE: {
        'de': {
            'question': 'Brauche ich eine Reiseversicherung?',
            'answer': 'Wir empfehlen eine Versicherung für medizinische Notfälle.',
        },
        'zh': {'question': '我需要购买旅游保险吗？', 'answer': '我们强烈建议购买旅游保险。'},
    },
}


@pytest.fixture
def faq_catalogue():
    with SessionLocal() as db:
        rows = {row.question: row for row in db.query(FAQ).filter(FAQ.question.in_(GENERATED))}
        before = {question: row.translations for question, row in rows.items()}
        for question, languages in GENERATED.items():
            rows[question].translations = {**(rows[question].translations or {}), **languages}
        db.commit()
        try:
            yield
        finally:
            for question, translations in before.items():
                rows[question].translations = translations
            db.commit()


def found(question):
    return [row['question'] for row in tools.search_company_faq.invoke({'question': question})]


@pytest.mark.parametrize(
    ('question', 'expected'),
    [
        # Russian, including the forms the exact word search missed.
        ('Нужна ли мне виза?', VISA),
        ('Как получить визу в Кыргызстан', VISA),
        ('безвизовый въезд', VISA),
        ('Обязательна ли страховка?', INSURANCE),
        ('хочу оформить страховку', INSURANCE),
        ('Можно ли оплатить картой?', CARD),
        ('вегетарианская еда', FOOD),
        ('едем с маленькими детьми', CHILDREN),
        ('где купить симку, сим карта', SIM),
        # A typo and Latin letters for a Russian word.
        ('страховкаа', INSURANCE),
        ('strakhovka', INSURANCE),
        # English.
        ('Do I need a visa?', VISA),
        ('Is travel insurance required?', INSURANCE),
        ('Can I pay with my credit card?', CARD),
        ('vegetarian meals', FOOD),
        ('travelling with children', CHILDREN),
        # German.
        ('Brauche ich ein Visum?', VISA),
        ('Ist eine Reiseversicherung nötig?', INSURANCE),
        # Chinese.
        ('需要签证吗', VISA),
        ('要买保险吗？', INSURANCE),
    ],
)
def test_question_in_any_language_finds_its_faq(faq_catalogue, question, expected):
    assert expected in found(question)[:3], found(question)


@pytest.mark.parametrize(
    'question',
    [
        'Продаёте ли вы криптовалюту?',
        'Xylophone quasar blockchain',
        'Fußballergebnisse der Bundesliga',
        '火星殖民计划',
        'Кыргызстан',  # occurs in most FAQ and says nothing
        'Можно ли?',
        'Hi',
        '',
    ],
)
def test_question_off_the_topic_finds_nothing(faq_catalogue, question):
    assert found(question) == []


def test_search_reads_the_whole_table_and_skips_hidden_rows():
    """The 31st question was invisible to the old search; inactive and demo rows stay hidden."""
    with SessionLocal() as db:
        fillers = [
            FAQ(question=f'Служебная запись {index}', answer='Заполнитель') for index in range(35)
        ]
        late = FAQ(question='Можно ли взять с собой квадрокоптер?', answer='Да, с разрешением.')
        hidden = FAQ(question='Квадрокоптер напрокат', answer='Снято.', is_active=False)
        demo = FAQ(question='ТЕСТ: квадрокоптер', answer='Демонстрация.')
        db.add_all([*fillers, late, hidden, demo])
        db.commit()
        created = [row.id for row in (*fillers, late, hidden, demo)]
    try:
        assert found('квадрокоптеры') == ['Можно ли взять с собой квадрокоптер?']
        assert len(found('служебная запись')) == 0  # a word of 35 rows is not a sign of any
    finally:
        with SessionLocal() as db:
            db.query(FAQ).filter(FAQ.id.in_(created)).delete(synchronize_session=False)
            db.commit()


def test_result_is_bounded():
    with SessionLocal() as db:
        total = db.query(FAQ).filter(FAQ.is_active.is_(True)).count()
    assert total >= 30
    assert len(found('аэропорт трансфер авиабилеты питание отель гид страховка виза')) <= 8
