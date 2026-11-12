import uuid
from datetime import UTC, datetime, timedelta

import pytest

from mysite.admin.overview import build_overview, label_positions, nice_top, plural
from mysite.api.admin import password_hash
from mysite.database.chat_models import ChatClient, ChatMessage, ChatSession
from mysite.database.db import SessionLocal
from mysite.database.models import (Admin, RequestStatusChoices, Tour, TourProgram, TourTranslation,
                                    TravelRequest)
from mysite.database.selection_models import TravelSelection

NOW = datetime(2031, 3, 15, 9, tzinfo=UTC)
PASSWORD = 'OverviewPassword123!'


def _client(db, created_at):
    client = ChatClient(
        username=f'overview_{uuid.uuid4().hex[:12]}', password_hash='x', created_at=created_at
    )
    db.add(client)
    db.flush()
    return client


def _questions(db, client, created_at, count):
    session = ChatSession(id=str(uuid.uuid4()), client_id=client.id, created_at=created_at)
    db.add(session)
    db.flush()
    for step in range(count):
        at = created_at + timedelta(minutes=step)
        db.add(ChatMessage(session_id=session.id, role='user', content='?', created_at=at))
        db.add(ChatMessage(session_id=session.id, role='assistant', content='!', created_at=at))


@pytest.fixture(scope='module')
def activity():
    with SessionLocal() as db:
        tour = Tour(title=f'Overview tour {uuid.uuid4().hex[:6]}', price=100, duration_days=2)
        db.add(tour)
        today = NOW - timedelta(hours=1)
        earlier = NOW - timedelta(days=3)
        previous = NOW - timedelta(days=9)
        first = _client(db, today)
        second = _client(db, earlier)
        _client(db, earlier)
        old = _client(db, previous)
        _questions(db, first, today, 3)
        _questions(db, second, earlier, 2)
        _questions(db, old, previous, 4)
        db.add(TravelSelection(client_id=first.id, tour_id=tour.id, created_at=today))
        db.add(TravelSelection(client_id=second.id, tour_id=tour.id, created_at=earlier))
        db.add(
            TravelRequest(
                client_id=first.id,
                name='Overview client',
                phone='+996700000001',
                status=RequestStatusChoices.in_progress,
                created_at=today,
            )
        )
        db.commit()
        yield tour.title


def _kpi(overview, key):
    return next(item for item in overview['kpis'] if item['key'] == key)


def test_overview_counts_the_period_and_compares_with_the_previous_one(activity):
    overview = build_overview('7', True, now=NOW)

    assert overview['range'] == '9 мар - 15 мар 2031'
    assert _kpi(overview, 'clients')['value'] == 3
    assert _kpi(overview, 'clients')['change']['text'] == '+2 к прошлому периоду'
    assert _kpi(overview, 'ai-users')['value'] == 2
    assert _kpi(overview, 'questions')['value'] == 5
    assert _kpi(overview, 'questions')['change']['text'] == '+1 к прошлому периоду'
    assert _kpi(overview, 'requests')['value'] == 1

    questions, clients, requests = overview['charts']
    assert [point['value'] for point in questions['points']] == [0, 0, 0, 2, 0, 0, 3]
    assert questions['points'][-1]['tip'] == '15 мар: 3 вопроса'
    assert clients['total'] == 3
    assert requests['total'] == 1

    assert [(step['label'], step['value']) for step in overview['funnel']] == [
        ('Зарегистрировались', 3),
        ('Написали ИИ-помощнику', 2),
        ('Собрали подборку', 2),
        ('Отправили заявку', 1),
    ]
    assert overview['interests'][0] == {'kind': 'Тур', 'name': activity, 'value': 2, 'width': 100.0}
    assert {item['label']: item['value'] for item in overview['statuses']}['В работе'] == 1


def test_overview_hides_client_requests_without_permission(activity):
    assert build_overview('7', False, now=NOW)['latest'] is None
    assert build_overview('unknown', True, now=NOW)['period'] == '30'


def test_overview_helpers_keep_axes_readable():
    assert [plural(number, ('вопрос', 'вопроса', 'вопросов')) for number in (1, 3, 11, 21, 25)] == [
        'вопрос',
        'вопроса',
        'вопросов',
        'вопрос',
        'вопросов',
    ]
    assert [nice_top(value) for value in (0, 3, 5, 9, 11, 45, 101)] == [4, 4, 6, 10, 20, 60, 200]
    marks = sorted(label_positions(30, 4))
    assert marks[-1] == 29
    assert all(later - earlier >= 5 for earlier, later in zip(marks, marks[1:], strict=False))


def _admin(role):
    username = f'overview-{role}'
    with SessionLocal() as db:
        admin = db.query(Admin).filter_by(username=username).first()
        if admin is None:
            admin = Admin(username=username, hashed_password=password_hash.hash(PASSWORD))
            db.add(admin)
        admin.role = role
        admin.is_active = True
        db.commit()
    return username


def _page(client, role, path='/admin/'):
    response = client.post(
        '/admin/login',
        data={'username': _admin(role), 'password': PASSWORD},
        follow_redirects=False,
    )
    assert response.status_code in (302, 303)
    try:
        page = client.get(path)
        assert page.status_code == 200
        return page.text
    finally:
        client.get('/admin/logout')


def test_overview_page_follows_admin_roles(client):
    manager = _page(client, 'manager')
    editor = _page(client, 'catalog_editor')

    for page in (manager, editor):
        assert 'Обзор' in page
        assert 'Путь клиента' in page
    assert 'Последние заявки' in manager
    assert 'Последние заявки' not in editor
    assert '/admin/travel-request/list' in manager
    assert '/admin/travel-request/list' not in editor
    assert '/admin/tour/list' in editor
    assert '/admin/tour/list' not in manager
    assert 'kt-nav-heading">Туры<' in editor
    assert 'kt-nav-heading">Туры<' not in manager


def test_admin_forms_show_readable_names(client):
    assert str(Admin(username='kerben')) == 'kerben'
    assert str(TourProgram(day_number=2, title='Сон-Куль')) == 'День 2. Сон-Куль'
    assert str(TourTranslation(lang='en', title='')) == 'EN'
    assert str(TravelSelection(id=5)) == '№5'
    page = _page(client, 'owner', '/admin/tour/create')
    assert 'Название' in page
    assert 'object at 0x' not in page
