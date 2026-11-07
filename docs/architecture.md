# Структура API Kerben Travel

## Основные части

```text
main.py                    создание FastAPI-приложения, middleware и подключение роутеров
mysite/api/                HTTP/WS-роуты, авторизация и прикладная логика
mysite/database/
  db.py                    SQLAlchemy engine, сессии и Base
  models.py                ORM-модели и связи
  schemas/                 Pydantic-контракты, разделённые по доменам
    admin.py               схемы входа и ответа администратору
    catalogue.py           туры, отели, транспорт, регионы и программы
    content.py             about, контакты и FAQ
    requests.py            заявки и выбранные услуги
  schema.py                совместимые экспорты старых импортов
alembic/                   миграции схемы базы данных
mysite/admin/              административный интерфейс и WebSocket-события
ML/                        изолированная логика агента, провайдера и инструментов
scripts/                   команды тестирования, форматирования и развёртывания
tests/unit/                изолированные unit-тесты без корневой DB-фикстуры
tests/                     интеграционные тесты приложения с PostgreSQL
```

Новый API-код должен импортировать схемы из доменных модулей `mysite.database.schemas.*`. Файл `mysite.database.schema` оставлен как совместимый фасад, чтобы старые импорты не ломались.

## Проверка изменений

1. Установить Python 3.12 и зависимости разработки из `requirements-dev.txt`.
2. Быстро проверить unit-тесты без БД: `python -B -m pytest --confcutdir=tests/unit tests/unit -q`.
3. Запустить полный набор: `python -m scripts.run_tests -q`. Без `TEST_DATABASE_URL` команда создаёт временную PostgreSQL в Docker Compose; с переменной использует явно выбранный тестовый сервер.
4. Перед отправкой проверить `ruff check .`, `python -m scripts.format_code --check` и `git diff --check`.

CI выполняет компиляционную проверку, Ruff/isort, аудит зависимостей, Bandit, изолированные тесты ML и запуска тестового harness, затем полный набор на PostgreSQL 17 с применением миграций до актуальной версии.
