import re
import uuid

from mysite.api.admin import password_hash
from mysite.database.db import SessionLocal
from mysite.database.models import FAQ, Admin, HelicopterImage, HelicopterTour

PASSWORD = 'FormsOwnerPassword123!'


def _owner(client):
    with SessionLocal() as db:
        admin = db.query(Admin).filter_by(username='forms-owner').first()
        if admin is None:
            admin = Admin(username='forms-owner', hashed_password=password_hash.hash(PASSWORD))
            db.add(admin)
        admin.role = 'owner'
        admin.is_active = True
        db.commit()
    client.post('/admin/login', data={'username': 'forms-owner', 'password': PASSWORD})


def test_create_form_hides_linked_records_and_automatic_fields(client):
    with SessionLocal() as db:
        tour = HelicopterTour(title=f'Existing flight {uuid.uuid4().hex[:6]}', price=400)
        db.add(tour)
        db.flush()
        db.add(HelicopterImage(helicopter_id=tour.id, image='/media/existing.webp'))
        db.commit()
        existing = tour.id
    _owner(client)
    try:
        page = client.get('/admin/helicopter-tour/create').text
        assert 'name="images"' not in page
        assert 'name="created_at"' not in page
        assert '.form-group:has([name="translations"])' in page
        assert re.search(r'<option[^>]*value="per_trip"[^>]*>за поездку</option>', page)
        created = client.post(
            '/admin/helicopter-tour/create',
            data={
                'title': 'Form flight',
                'price': '450',
                'price_unit': 'per_trip',
                'is_active': 'y',
                'translations': '{}',
                'save': 'Save',
            },
            follow_redirects=False,
        )
        assert created.status_code in (302, 303), created.text
        with SessionLocal() as db:
            assert db.query(HelicopterImage).filter_by(helicopter_id=existing).count() == 1
            assert db.query(HelicopterTour).filter_by(title='Form flight').one().price == 450
    finally:
        client.get('/admin/logout')


def test_edit_form_keeps_manual_translation_and_lists_show_local_time(client):
    with SessionLocal() as db:
        faq = FAQ(question=f'Forms question {uuid.uuid4().hex[:6]}', answer='Answer')
        db.add(faq)
        db.commit()
        identity = faq.id
    _owner(client)
    try:
        edit = client.get(f'/admin/faq/edit/{identity}').text
        assert 'name="translations"' in edit
        assert '.form-group:has([name="translations"])' not in edit
        roles = client.get('/admin/admin/list').text
        assert 'Владелец' in roles
        sessions = client.get('/admin/admin-session/list').text
        assert re.search(r'\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}', sessions)
        assert '+00:00' not in sessions
    finally:
        client.get('/admin/logout')


def test_list_rows_have_labelled_actions(client):
    _owner(client)
    try:
        page = client.get('/admin/faq/list').text
        assert "content: 'Изменить'" in page
        assert "content: 'Удалить'" in page
        assert "Edit: 'Изменить запись'" in page
        assert "Edit: 'Изменить запись'" not in client.get('/admin/faq/create').text
    finally:
        client.get('/admin/logout')
