from pathlib import Path


def test_required_deployment_files_exist():
    assert Path('requirements.txt').is_file()
    assert Path('.env.example').is_file()
    assert Path('DEPLOY.md').is_file()


def test_requirements_cover_runtime_dependencies():
    requirements = Path('requirements.txt').read_text(encoding='utf-8').lower()
    required = {
        'alembic',
        'fastapi',
        'itsdangerous',
        'langchain-google-genai',
        'psycopg2-binary',
        'pwdlib',
        'python-dotenv',
        'pyjwt',
        'python-multipart',
        'sqladmin',
        'sqlalchemy',
        'uvicorn',
    }
    assert all(package in requirements for package in required)


def test_environment_example_documents_required_settings():
    example = Path('.env.example').read_text(encoding='utf-8')
    required = {
        'SECRET_KEY',
        'DATABASE_URL',
        'GEMINI_API_KEY',
        'GEMINI_MODEL',
        'CORS_ALLOWED_ORIGINS',
        'CHAT_ALLOWED_ORIGINS',
    }
    names = {
        line.split('=', 1)[0].strip()
        for line in example.splitlines()
        if line.strip() and not line.lstrip().startswith('#') and '=' in line
    }
    assert required <= names


def test_local_runtime_artifacts_are_ignored():
    patterns = Path('.gitignore').read_text(encoding='utf-8').splitlines()
    assert 'venv/' in patterns
    assert '.test_*.db' in patterns
