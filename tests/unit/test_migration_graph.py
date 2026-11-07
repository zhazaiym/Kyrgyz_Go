import ast
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parents[2]


def _revision_ids():
    ids = []
    for path in sorted((ROOT / 'alembic' / 'versions').glob('*.py')):
        for node in ast.parse(path.read_text(encoding='utf-8')).body:
            if isinstance(node, ast.Assign) and any(
                getattr(target, 'id', None) == 'revision' for target in node.targets
            ):
                ids.append(ast.literal_eval(node.value))
    return ids


def test_migration_revision_ids_are_unique():
    ids = _revision_ids()
    assert ids
    assert sorted({rev for rev in ids if ids.count(rev) > 1}) == []


def test_migrations_have_a_single_head():
    script = ScriptDirectory.from_config(Config(str(ROOT / 'alembic.ini')))
    heads = script.get_heads()
    assert len(heads) == 1, heads
