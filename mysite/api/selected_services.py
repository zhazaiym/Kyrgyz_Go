"""Validated catalogue snapshots for booking previews and stored requests."""

from mysite.database.models import Hotel, Tour, Transport


def selected_services(db, state):
    snapshot, missing = [], []
    for kind, model, field in (
        ('tour', Tour, 'title'),
        ('hotel', Hotel, 'name'),
        ('transport', Transport, 'name'),
    ):
        identity = state.get(f'{kind}_id')
        if identity is None:
            continue
        item = db.get(model, identity) if type(identity) is int and identity > 0 else None
        if not item or not item.is_active:
            missing.append(f'valid_{kind}')
        else:
            snapshot.append({'kind': kind, 'id': item.id, 'name': getattr(item, field)})
    return snapshot, missing
