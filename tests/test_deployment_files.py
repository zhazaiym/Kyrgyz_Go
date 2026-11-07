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
    assert 'Admin pages are reachable from any IP' in example
    assert 'ADMIN_ALLOWED_IPS' not in names


def test_chat_websocket_example_allows_the_production_site():
    example = Path('.env.example').read_text(encoding='utf-8')
    settings = {
        line.split('=', 1)[0].strip(): line.split('=', 1)[1].strip()
        for line in example.splitlines()
        if line.strip() and not line.lstrip().startswith('#') and '=' in line
    }
    allowed = {origin.strip() for origin in settings['CHAT_ALLOWED_ORIGINS'].split(';')}
    assert 'https://kerben-travel.vercel.app' in allowed
    cors = {origin.strip() for origin in settings['CORS_ALLOWED_ORIGINS'].split(';')}
    assert 'https://kerben-travel.vercel.app' in cors


def test_dead_frontends_and_old_server_are_not_configured():
    dead = ('tours-app-teal.vercel.app', 'kyrgyzgo-admin.vercel.app', '13.53.40.37')
    for name in ('.env.example', 'DEPLOY.md', 'API.md', 'docker-compose.yml', 'README.md'):
        text = Path(name).read_text(encoding='utf-8')
        for value in dead:
            assert value not in text, (name, value)


def test_local_runtime_artifacts_are_ignored():
    patterns = Path('.gitignore').read_text(encoding='utf-8').splitlines()
    assert 'venv/' in patterns
    assert '.test_*.db' in patterns
