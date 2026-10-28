"""Track source fields and manual overrides for catalogue translations.

The migration deliberately carries a frozen field list and hash implementation:
Alembic migrations must not depend on importable application code or API secrets.
"""

import hashlib

import sqlalchemy as sa

from alembic import op

revision = '20261028_0014'
down_revision = '20261028_0013'
branch_labels = None
depends_on = None

# Snapshot of localized columns at the time this migration was authored.
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


def _field_hash(value):
    normalized = '' if value is None or value == '' else value
    return hashlib.md5(str(normalized).encode('utf-8'), usedforsecurity=False).hexdigest()


def _matches_source(stored_hash, source):
    # Accept the original 0014 identity and the normalized identity used by
    # later application versions, without importing mutable application code.
    normalized = (
        source.replace('\r\n', '\n').replace('\r', '\n') if isinstance(source, str) else source
    )
    return stored_hash in (_field_hash(source), _field_hash(normalized))


def upgrade():
    op.add_column(
        'tour_translations',
        sa.Column('source_hashes', sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column(
        'tour_translations',
        sa.Column('manual_fields', sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )

    bind = op.get_bind()
    for table_name, fields in CONTENT_FIELDS.items():
        columns = [sa.column('id', sa.Integer)]
        columns.extend(sa.column(field, sa.Text) for field in fields)
        columns.append(sa.column('translations', sa.JSON))
        content = sa.table(table_name, *columns)
        updates = []
        for row in (
            bind.execute(sa.select(*columns).order_by(content.c.id)).mappings().yield_per(500)
        ):
            translations = row['translations']
            if not isinstance(translations, dict):
                continue
            updated = dict(translations)
            changed = False
            source = {field: row[field] for field in fields}
            for language in LANGUAGES:
                values = updated.get(language)
                if not isinstance(values, dict):
                    continue
                values = dict(values)
                raw_hashes = values.get('_source_hashes', {})
                hashes = dict(raw_hashes) if isinstance(raw_hashes, dict) else {}
                for field in fields:
                    if isinstance(values.get(field), str) and values[field]:
                        hashes.setdefault(field, _field_hash(source[field]))
                values['_source_hashes'] = hashes
                updated[language] = values
                changed = True
            if changed:
                updates.append({'row_id': row['id'], 'translations': updated})
        if updates:
            bind.execute(content.update().where(content.c.id == sa.bindparam('row_id')), updates)

    translation = sa.table(
        'tour_translations',
        sa.column('id', sa.Integer),
        sa.column('tour_id', sa.Integer),
        sa.column('title', sa.Text),
        sa.column('description', sa.Text),
        sa.column('included', sa.Text),
        sa.column('excluded', sa.Text),
        sa.column('source_hashes', sa.JSON),
    )
    tour = sa.table(
        'tours', sa.column('id', sa.Integer), *(sa.column(field, sa.Text) for field in TOUR_FIELDS)
    )
    join = translation.join(tour, translation.c.tour_id == tour.c.id)
    selected = (
        sa.select(
            *translation.c, *(tour.c[field].label(f'source_{field}') for field in TOUR_FIELDS)
        )
        .select_from(join)
        .order_by(translation.c.id)
    )
    updates = []
    for row in bind.execute(selected).mappings().yield_per(500):
        hashes = dict(row['source_hashes'] or {})
        for field in TOUR_FIELDS:
            if isinstance(row[field], str) and row[field]:
                hashes.setdefault(field, _field_hash(row[f'source_{field}']))
        updates.append({'row_id': row['id'], 'source_hashes': hashes})
    if updates:
        bind.execute(
            translation.update().where(translation.c.id == sa.bindparam('row_id')), updates
        )


def downgrade():
    bind = op.get_bind()
    for table_name, fields in CONTENT_FIELDS.items():
        columns = [sa.column('id', sa.Integer)]
        columns.extend(sa.column(field, sa.Text) for field in fields)
        columns.append(sa.column('translations', sa.JSON))
        content = sa.table(table_name, *columns)
        updates = []
        for row in (
            bind.execute(sa.select(*columns).order_by(content.c.id)).mappings().yield_per(500)
        ):
            translations = row['translations']
            if not isinstance(translations, dict):
                continue
            updated = dict(translations)
            changed = False
            source = {field: row[field] for field in fields}
            for language in LANGUAGES:
                values = updated.get(language)
                if not isinstance(values, dict):
                    continue
                values = dict(values)
                hashes = values.get('_source_hashes', {})
                hashes = hashes if isinstance(hashes, dict) else {}
                for field in fields:
                    if field in values and not _matches_source(hashes.get(field), source[field]):
                        values.pop(field, None)
                        changed = True
                values.pop('_source_hashes', None)
                values.pop('_manual_fields', None)
                if values:
                    updated[language] = values
                else:
                    updated.pop(language, None)
                changed = True
            if changed:
                updates.append({'row_id': row['id'], 'translations': updated or None})
        if updates:
            bind.execute(content.update().where(content.c.id == sa.bindparam('row_id')), updates)

    translation = sa.table(
        'tour_translations',
        sa.column('id', sa.Integer),
        sa.column('tour_id', sa.Integer),
        *(sa.column(field, sa.Text) for field in TOUR_FIELDS),
        sa.column('source_hashes', sa.JSON),
    )
    tour = sa.table(
        'tours', sa.column('id', sa.Integer), *(sa.column(field, sa.Text) for field in TOUR_FIELDS)
    )
    join = translation.join(tour, translation.c.tour_id == tour.c.id)
    selected = sa.select(
        translation.c.id,
        *(translation.c[field] for field in TOUR_FIELDS),
        translation.c.source_hashes,
        *(tour.c[field].label(f'source_{field}') for field in TOUR_FIELDS),
    ).select_from(join)
    for row in bind.execute(selected).mappings().yield_per(500):
        hashes = row['source_hashes'] or {}
        values = {'id': row['id']}
        for field in TOUR_FIELDS:
            if not _matches_source(hashes.get(field), row[f'source_{field}']):
                # Legacy readers treat any non-empty text as translated. Clear
                # stale values instead of copying the source into translation.
                values[field] = '' if field == 'title' else None
        if len(values) > 1:
            identity = values.pop('id')
            bind.execute(translation.update().where(translation.c.id == identity).values(**values))

    op.drop_column('tour_translations', 'manual_fields')
    op.drop_column('tour_translations', 'source_hashes')
