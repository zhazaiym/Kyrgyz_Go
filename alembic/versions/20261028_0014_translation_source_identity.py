"""Track source fields and manual overrides for catalogue translations.

Keep the field map and normalization here frozen. Alembic revisions must not
import live application modules, whose dependencies and contents can change.
"""

import hashlib

import sqlalchemy as sa

from alembic import op

revision = '20261028_0014'
down_revision = '20261028_0013'
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


def source_hash(value):
    normalized = '' if value is None or value == '' else value
    if isinstance(normalized, str):
        normalized = normalized.replace('\r\n', '\n').replace('\r', '\n')
    return hashlib.md5(str(normalized).encode('utf-8'), usedforsecurity=False).hexdigest()


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
        selected = sa.select(*columns).order_by(content.c.id)
        updates = []
        for row in bind.execute(selected).mappings().yield_per(500):
            translations = row['translations']
            if not isinstance(translations, dict):
                continue
            updated = dict(translations)
            changed = False
            source = {field: row[field] for field in fields}
            for language in ('en', 'de', 'zh'):
                values = updated.get(language)
                if not isinstance(values, dict):
                    continue
                values = dict(values)
                hashes = dict(values.get('_source_hashes', {}))
                for field in fields:
                    if isinstance(values.get(field), str) and values[field]:
                        hashes.setdefault(field, source_hash(source[field]))
                values['_source_hashes'] = hashes
                updated[language] = values
                changed = True
            if changed:
                updates.append({'row_id': row['id'], 'translations': updated})
        if updates:
            bind.execute(content.update().where(content.c.id == sa.bindparam('row_id')), updates)

    tour_translation = sa.table(
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
    join = tour_translation.join(tour, tour_translation.c.tour_id == tour.c.id)
    source_columns = [tour.c[field].label(f'source_{field}') for field in TOUR_FIELDS]
    selected = (
        sa.select(*tour_translation.c, *source_columns)
        .select_from(join)
        .order_by(tour_translation.c.id)
    )
    updates = []
    for row in bind.execute(selected).mappings().yield_per(500):
        hashes = dict(row['source_hashes'] or {})
        for field in TOUR_FIELDS:
            if isinstance(row[field], str) and row[field]:
                hashes.setdefault(field, source_hash(row[f'source_{field}']))
        updates.append({'row_id': row['id'], 'source_hashes': hashes})
    if updates:
        bind.execute(
            tour_translation.update().where(tour_translation.c.id == sa.bindparam('row_id')),
            updates,
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
            for language in ('en', 'de', 'zh'):
                values = updated.get(language)
                if not isinstance(values, dict):
                    continue
                values = dict(values)
                hashes = values.get('_source_hashes', {})
                for field in fields:
                    translated = values.get(field)
                    if (
                        isinstance(translated, str)
                        and translated
                        and hashes.get(field) != source_hash(row[field])
                    ):
                        values.pop(field, None)
                        changed = True
                values.pop('_source_hashes', None)
                values.pop('_manual_fields', None)
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
    tours = sa.table(
        'tours', sa.column('id', sa.Integer), *(sa.column(field, sa.Text) for field in TOUR_FIELDS)
    )
    join = translation.join(tours, translation.c.tour_id == tours.c.id)
    source_columns = [tours.c[field].label(f'source_{field}') for field in TOUR_FIELDS]
    rows = bind.execute(
        sa.select(*translation.c, *source_columns).select_from(join).order_by(translation.c.id)
    ).mappings()
    stale_ids = []
    for row in rows:
        hashes = row['source_hashes'] or {}
        if any(
            isinstance(row[field], str)
            and row[field]
            and hashes.get(field) != source_hash(row[f'source_{field}'])
            for field in TOUR_FIELDS
        ):
            stale_ids.append(row['id'])
    if stale_ids:
        bind.execute(translation.delete().where(translation.c.id.in_(stale_ids)))

    op.drop_column('tour_translations', 'manual_fields')
    op.drop_column('tour_translations', 'source_hashes')
