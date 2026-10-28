"""Format Python code with Ruff and compact import groups with isort."""

import argparse
import subprocess
import sys
from pathlib import Path

import isort

ROOT = Path(__file__).resolve().parents[1]


def format_code(path, config):
    source = path.read_text(encoding='utf-8')
    result = subprocess.run(
        [sys.executable, '-m', 'ruff', 'format', '--stdin-filename', str(path), '-'],
        input=source,
        capture_output=True,
        text=True,
        encoding='utf-8',
        check=True,
        cwd=ROOT,
    )
    return source, isort.code(result.stdout, config=config)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Check without changing files')
    options = parser.parse_args()
    config = isort.Config(settings_file=str(ROOT / 'pyproject.toml'))
    result = subprocess.run(
        [sys.executable, '-m', 'ruff', 'check', '--show-files', '.'],
        capture_output=True,
        text=True,
        encoding='utf-8',
        check=True,
        cwd=ROOT,
    )
    changed = 0
    for name in result.stdout.splitlines():
        path = Path(name)
        if path.suffix != '.py':
            continue
        source, formatted = format_code(path, config)
        if source == formatted:
            continue
        changed += 1
        print(path.relative_to(ROOT))
        if not options.check:
            with path.open('w', encoding='utf-8', newline='\n') as output:
                output.write(formatted)
    print(f'{changed} files {"need formatting" if options.check else "formatted"}.')
    return int(options.check and changed > 0)


if __name__ == '__main__':
    raise SystemExit(main())
