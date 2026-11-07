"""Normalize catalogue source line endings and preserve current translation hashes."""

import hashlib

import sqlalchemy as sa

from alembic import op

revision = '20261028_0016'
down_revision = '20261028_0015'
branch_labels = None
depends_on = None

CONTENT_FIELDS = {
    'abouts': ('title', 'description'),
    'about_sections': ('title', 'description'),
    'tour_categories': ('name',),
    'countries': ('name',),
    'regions': ('name',),
    'districts': ('name',),
    'hotels': ('name', 'description', 'address'),
    'transports': ('name', 'description', 'color'),
    'helicopter_tours': (
        'title',
        'description',
        'destination',
        'departure_location',
        'instruction',
        'included',
    ),
    'trekkings': ('title', 'description', 'route', 'included', 'requirements', 'difficulty'),
    'faqs': ('question', 'answer'),
    'contacts': ('country', 'city', 'address'),
    'tour_programs': ('title', 'description'),
    'trekking_programs': ('title', 'description'),
}
TOUR_FIELDS = ('title', 'description', 'included', 'excluded')
LANGUAGES = ('en', 'de', 'zh')


def _normalize(value):
    return value.replace('\r\n', '\n').replace('\r', '\n') if isinstance(value, str) else value


def _hash(value):
    normalized = '' if value is None or value == '' else value
    normalized = _normalize(normalized)
    return hashlib.md5(str(normalized).encode('utf-8'), usedforsecurity=False).hexdigest()


def _raw_hash(value):
    normalized = '' if value is None or value == '' else value
    return hashlib.md5(str(normalized).encode('utf-8'), usedforsecurity=False).hexdigest()


def upgrade():
    bind = op.get_bind()
    for table_name, fields in CONTENT_FIELDS.items():
        columns = [sa.column('id', sa.Integer)]
        columns.extend(sa.column(field, sa.Text) for field in fields)
        columns.append(sa.column('translations', sa.JSON))
        table = sa.table(table_name, *columns)
        updates = []
        has_cr = sa.or_(*(table.c[field].like('%\r%') for field in fields))
        rows = (
            bind.execute(sa.select(*columns).where(has_cr).order_by(table.c.id))
            .mappings()
            .yield_per(500)
        )
        for row in rows:
            source = {field: row[field] for field in fields}
            normalized = {field: _normalize(value) for field, value in source.items()}
            changes = {'row_id': row['id']}
            changes.update(
                {field: value for field, value in normalized.items() if value != source[field]}
            )
            translations = row['translations']
            changed_translations = False
            if isinstance(translations, dict):
                translations = dict(translations)
                for language in LANGUAGES:
                    values = translations.get(language)
                    if not isinstance(values, dict):
                        continue
                    values = dict(values)
                    hashes = values.get('_source_hashes')
                    if not isinstance(hashes, dict):
                        continue
                    hashes = dict(hashes)
                    language_changed = False
                    for field in fields:
                        if (
                            hashes.get(field) == _raw_hash(source[field])
                            and normalized[field] != source[field]
                        ):
                            hashes[field] = _hash(normalized[field])
                            changed_translations = True
                            language_changed = True
                    if language_changed:
                        values['_source_hashes'] = hashes
                        translations[language] = values
                if changed_translations:
                    changes['translations'] = translations
            if len(changes) > 1:
                updates.append(changes)
        if updates:
            statement = table.update().where(table.c.id == sa.bindparam('row_id'))
            for values in updates:
                bind.execute(statement, values)

    translation = sa.table(
        'tour_translations',
        sa.column('id', sa.Integer),
        sa.column('tour_id', sa.Integer),
        *(sa.column(field, sa.Text) for field in TOUR_FIELDS),
        sa.column('source_hashes', sa.JSON),
    )
    tour = sa.table(
        'tours', sa.column('id', sa.Integer), *(sa.column(f, sa.Text) for f in TOUR_FIELDS)
    )
    joined = translation.join(tour, translation.c.tour_id == tour.c.id)
    selected = (
        sa.select(
            *translation.c, *(tour.c[field].label(f'source_{field}') for field in TOUR_FIELDS)
        )
        .select_from(joined)
        .where(sa.or_(*(tour.c[field].like('%\r%') for field in TOUR_FIELDS)))
    )
    updates = []
    for row in bind.execute(selected).mappings().yield_per(500):
        hashes = dict(row['source_hashes'] or {})
        changed_hash = False
        for field in TOUR_FIELDS:
            source = row[f'source_{field}']
            normalized = _normalize(source)
            if normalized != source:
                if hashes.get(field) == _raw_hash(source):
                    hashes[field] = _hash(normalized)
                    changed_hash = True
        if changed_hash:
            updates.append({'row_id': row['id'], 'source_hashes': hashes})
    if updates:
        statement = translation.update().where(translation.c.id == sa.bindparam('row_id'))
        for values in updates:
            bind.execute(statement, values)

    source_columns = [sa.column('id', sa.Integer)]
    source_columns.extend(sa.column(field, sa.Text) for field in TOUR_FIELDS)
    tours = sa.table('tours', *source_columns)
    contains_cr = sa.or_(*(tours.c[field].like('%\r%') for field in TOUR_FIELDS))
    normalized_tours = []
    for row in (
        bind.execute(sa.select(*source_columns).where(contains_cr).order_by(tours.c.id))
        .mappings()
        .yield_per(500)
    ):
        values = {'row_id': row['id']}
        for field in TOUR_FIELDS:
            value = row[field]
            normalized = _normalize(value)
            if normalized != value:
                values[field] = normalized
        if len(values) > 1:
            normalized_tours.append(values)
    if normalized_tours:
        statement = tours.update().where(tours.c.id == sa.bindparam('row_id'))
        for values in normalized_tours:
            bind.execute(statement, values)


def downgrade():
    # Line-ending normalization is data-preserving and intentionally irreversible.
    pass
