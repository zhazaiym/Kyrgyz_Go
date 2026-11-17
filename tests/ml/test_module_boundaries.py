"""The dependency goes one way: mysite calls ML, ML imports nothing from mysite."""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ML_FILES = sorted((ROOT / 'ML').glob('*.py'))


def imported_modules(node):
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if isinstance(node, ast.ImportFrom):
        return [node.module or '']
    return []


@pytest.mark.parametrize('path', ML_FILES, ids=lambda path: path.name)
def test_ml_does_not_import_the_application(path):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    forbidden = [
        (node.lineno, name)
        for node in ast.walk(tree)
        for name in imported_modules(node)
        if name == 'mysite' or name.startswith('mysite.') or name == 'main'
    ]
    assert not forbidden, f'{path.name} imports the application: {forbidden}'


@pytest.mark.parametrize('path', ML_FILES, ids=lambda path: path.name)
def test_ml_has_no_imports_hidden_inside_functions(path):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    hidden = [
        (inner.lineno, imported_modules(inner))
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        for inner in ast.walk(node)
        if isinstance(inner, (ast.Import, ast.ImportFrom))
    ]
    assert not hidden, f'{path.name} imports inside a function: {hidden}'


def test_translator_is_an_ordinary_module():
    source = (ROOT / 'mysite' / 'translations' / 'translator.py').read_text(encoding='utf-8')
    assert 'sys.modules' not in source and 'import_module' not in source


def test_translation_reply_is_not_repaired_by_hand():
    source = (ROOT / 'ML' / 'translation.py').read_text(encoding='utf-8')
    assert 'json.loads' not in source
    assert 'import re' not in source and 're.compile' not in source
