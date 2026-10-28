"""Track source fields and manual overrides for catalogue translations."""

import sqlalchemy as sa

from alembic import op

revision = '20261028_0014'
down_revision = '20261028_0013'
branch_labels = None
depends_on = None


def upgrade():
    from mysite.translations.content import CONTENT_FIELDS
    from mysite.translations.source import TOUR_TRANSLATION_FIELDS, source_field_hash

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
                        hashes.setdefault(field, source_field_hash(source[field]))
                values['_source_hashes'] = hashes
                updated[language] = values
                changed = True
            if changed:
                updates.append({'id': row['id'], 'translations': updated})
        if updates:
            bind.execute(content.update().where(content.c.id == sa.bindparam('id')), updates)

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
        'tours',
        sa.column('id', sa.Integer),
        *(sa.column(field, sa.Text) for field in TOUR_TRANSLATION_FIELDS),
    )
    join = tour_translation.join(tour, tour_translation.c.tour_id == tour.c.id)
    source_columns = [tour.c[field].label(f'source_{field}') for field in TOUR_TRANSLATION_FIELDS]
    selected = (
        sa.select(*tour_translation.c, *source_columns)
        .select_from(join)
        .order_by(tour_translation.c.id)
    )
    updates = []
    for row in bind.execute(selected).mappings().yield_per(500):
        hashes = dict(row['source_hashes'] or {})
        for field in TOUR_TRANSLATION_FIELDS:
            if isinstance(row[field], str) and row[field]:
                hashes.setdefault(field, source_field_hash(row[f'source_{field}']))
        updates.append({'id': row['id'], 'source_hashes': hashes})
    if updates:
        bind.execute(
            tour_translation.update().where(tour_translation.c.id == sa.bindparam('id')), updates
        )


def downgrade():
    op.drop_column('tour_translations', 'manual_fields')
    op.drop_column('tour_translations', 'source_hashes')
