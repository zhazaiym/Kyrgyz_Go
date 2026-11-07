"""Populate Kerben Travel FAQ content in Russian and English."""

import hashlib

import sqlalchemy as sa

from alembic import op
from mysite.faq_content import FAQ_CONTENT

revision = '20261030_0020'
down_revision = '20261030_0019'
branch_labels = None
depends_on = None


def _hash(value):
    return hashlib.md5(value.encode('utf-8'), usedforsecurity=False).hexdigest()


def upgrade():
    faq = sa.table(
        'faqs',
        sa.column('id', sa.Integer),
        sa.column('question', sa.Text),
        sa.column('answer', sa.Text),
        sa.column('order', sa.Integer),
        sa.column('is_active', sa.Boolean),
        sa.column('translations', sa.JSON),
    )
    op.execute(faq.delete())
    op.bulk_insert(
        faq,
        [
            {
                'question': entry['question'],
                'answer': entry['answer'],
                'order': index,
                'is_active': True,
                'translations': {
                    'en': {
                        'question': entry['question_en'],
                        'answer': entry['answer_en'],
                        '_source_hashes': {
                            'question': _hash(entry['question']),
                            'answer': _hash(entry['answer']),
                        },
                        '_manual_fields': ['question', 'answer'],
                    }
                },
            }
            for index, entry in enumerate(FAQ_CONTENT, start=1)
        ],
    )


def downgrade():
    op.execute(sa.text('DELETE FROM faqs'))
