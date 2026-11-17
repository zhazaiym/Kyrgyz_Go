import pytest

from mysite.database import models as m
from mysite.database.db import SessionLocal


@pytest.mark.parametrize(
    'path,changes',
    [
        ('/tours/', {'title': 'x' * 256}),
        ('/tours/', {'title': '   '}),
        ('/tours/', {'price': '-1'}),
        ('/tours/', {'price': '10000000000'}),
        ('/tours/', {'price': '12.345'}),
        ('/tours/', {'min_people': 4, 'max_people': 2}),
        ('/tours/', {'duration_days': 0}),
        ('/tours/', {'price': None}),
        ('/hotels/', {'stars': 6}),
        ('/hotels/', {'name': 'x' * 256}),
        ('/transports/', {'seats': 0}),
        ('/transports/', {'seats': 2**31}),
        ('/transports/', {'main_image': 'javascript:alert(1)'}),
        ('/helicopter-tours/', {'duration_minutes': -1}),
        ('/trekkings/', {'price': -2}),
        ('/contacts/', {'email': 'invalid-email'}),
    ],
)
def test_invalid_storage_values_are_rejected_before_postgresql(path, changes):
    with SessionLocal() as db:
        region = m.Region(name='Boundary region')
        district = m.District(name='Boundary district', region=region)
        db.add_all([region, district])
        db.commit()
        location = {'region_id': region.id, 'district_id': district.id}
    base = {
        '/tours/': {'title': 'Boundary tour', 'price': 10},
        '/hotels/': {'name': 'Boundary hotel', 'price': 10, **location},
        '/transports/': {'name': 'Boundary van', 'seats': 4, 'price': 10},
        '/helicopter-tours/': {'title': 'Boundary flight', 'price': 10},
        '/trekkings/': {'title': 'Boundary trek', 'price': 10},
        '/contacts/': {'city': 'Boundary city'},
    }[path]
    model = {
        '/tours/': m.Tour,
        '/hotels/': m.Hotel,
        '/transports/': m.Transport,
        '/helicopter-tours/': m.HelicopterTour,
        '/trekkings/': m.Trekking,
        '/contacts/': m.Contact,
    }[path]
    with SessionLocal() as db:
        db.add(model(**{**base, **changes}))
        with pytest.raises(ValueError):
            db.flush()


def test_partial_group_update_checks_existing_other_bound(seed):
    identity = seed(m.Tour, title='Group boundaries', price=10, min_people=1, max_people=4)
    with SessionLocal() as db:
        db.get(m.Tour, identity).min_people = 5
        with pytest.raises(ValueError):
            db.flush()
    with SessionLocal() as db:
        assert db.get(m.Tour, identity).min_people == 1
