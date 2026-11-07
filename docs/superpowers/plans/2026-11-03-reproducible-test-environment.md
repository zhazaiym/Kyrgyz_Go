# План реализации воспроизводимых тестов

> **For agentic workers:** Выполнять inline, по одному заданию за раз; не запускать задачи параллельно, потому что они меняют один тестовый запускатель и его конфигурацию.

**Цель:** Сделать безопасный единый запуск полного набора тестов локально и в GitHub Actions с PostgreSQL.

**Архитектура:** Запускатель `scripts.run_tests` принимает явный `TEST_DATABASE_URL` или поднимает изолированную тестовую PostgreSQL через Compose. Тестовая фикстура использует только явно заданный URL и создаёт/удаляет отдельную временную базу. CI использует уже поднятый PostgreSQL service и вызывает тот же запускатель.

**Технологии:** Python 3.12, pytest, SQLAlchemy, PostgreSQL 17, Docker Compose, GitHub Actions.

## Глобальные ограничения

- Не читать `DATABASE_URL` или `.env` как источник подключения тестов.
- Не запускать тесты против production или базы приложения.
- Не менять API, модели, миграции или production deployment.
- Любой тестовый запуск должен удалять только временную базу с префиксом `test_kyrgyzgo_` и, в локальном Compose-режиме, принадлежащий ему контейнер без постоянного volume.
- При отсутствии тестовой PostgreSQL завершаться понятной ошибкой до подключения.

---

### Задача 1: Закрепить безопасную конфигурацию тестовой БД

**Файлы:**
- Изменить: `tests/postgres_support.py`
- Создать: `tests/unit/test_postgres_support.py`

**Интерфейс:** `temporary_database()` без аргументов читает исключительно `TEST_DATABASE_URL`; если переменная отсутствует — выбрасывает `RuntimeError` с инструкцией. Неподдерживаемая схема также отклоняется до создания соединения.

- [x] Добавить тест, который очищает `TEST_DATABASE_URL`, задаёт `DATABASE_URL` и проверяет, что `temporary_database().__enter__()` завершается ожидаемым `RuntimeError`, не создавая engine.
- [x] Добавить тест, что URL с backend не PostgreSQL отвергается до подключения.
- [x] Запустить тесты командой `python -m pytest --confcutdir=tests/unit tests/unit/test_postgres_support.py -q`, чтобы pytest не загружал `tests/conftest.py` с подключением к PostgreSQL.
- [x] Удалить fallback на `DATABASE_URL` и чтение dotenv из `tests/postgres_support.py`, сохранив создание/удаление случайной базы и гарантию её имени.
- [x] Повторить unit-тесты и проверить ошибки конфигурации.

### Задача 2: Добавить локальную временную PostgreSQL

**Файлы:**
- Создать: `docker-compose.test.yml`
- Создать: `scripts/run_tests.py`
- Создать: `tests/unit/test_run_tests.py`
- Изменить: `requirements-dev.txt`

**Интерфейс:** `python -m scripts.run_tests [pytest args...]`. При `TEST_DATABASE_URL` запускает pytest напрямую. Без URL запускает сервис `postgres` из `docker-compose.test.yml`, ждёт healthcheck, задаёт URL `postgresql+psycopg2://postgres:postgres@127.0.0.1:55432/postgres`, запускает pytest и всегда останавливает принадлежащий этому запуску сервис командой `docker compose down --remove-orphans`. Compose-файл не объявляет volumes; порт 55432 можно переопределить через `TEST_POSTGRES_PORT`.

- [x] Сначала покрыть unit-тестами построение команды pytest, передачу явного URL и решение использовать внешний URL без вызова Docker.
- [x] Добавить тесты очистки после ненулевого кода pytest, ошибки старта и прерывания процесса.
- [x] Запустить `python -m pytest --confcutdir=tests/unit tests/unit/test_run_tests.py -q`; ожидается сначала падение на отсутствующем запускателе.
- [x] Реализовать запускатель через `subprocess.run`, передавая аргументы pytest и окружение процессу, не меняя процессное окружение Python глобально.
- [x] В Compose-файле использовать `postgres:17`, отдельный сервис и healthcheck; привязать порт к loopback `127.0.0.1:${TEST_POSTGRES_PORT:-55432}:5432`, хранение данных не монтировать в постоянный volume.
- [x] Закрепить `pytest==9.2.0` в `requirements-dev.txt`, чтобы CI и локальная установка использовали одну версию.
- [x] Проверить unit-тесты с замоканными вызовами subprocess; убедиться, что внешний URL не вызывает `up`/`down`, а локальный режим всегда вызывает `down`.

### Задача 3: Перевести CI на общий запускатель

**Файлы:**
- Изменить: `.github/workflows/ci.yml`
- Изменить/добавить: `tests/unit/test_run_tests.py`

- [ ] Сохранить PostgreSQL service, healthcheck и `TEST_DATABASE_URL` CI.
- [x] Заменить прямой `python -m pytest -q` на `python -m scripts.run_tests -q`; остальные проверки CI оставить без изменений.
- [x] Добавить изолированный запуск unit-тестов тестового инструментария в CI.
- [x] Разобрать workflow через PyYAML, проверить Compose-файл командой `docker compose config --quiet` и проверить изменённые Python-файлы. `actionlint` в окружении отсутствует.
- [x] Проверить unit-тесты запускателя; полный набор пока недоступен, так как Docker daemon не запущен.

### Задача 4: Документировать команды и ограничения

**Файлы:**
- Создать: `docs/local-testing.md`
- Изменить: `docs/README.md`
- Изменить: `docs/code-style.md`, `docs/chat-booking-check.md`, `docs/chat-efficiency.md`

- [x] Описать рекомендуемую команду `python -m scripts.run_tests`, требования Python/Docker Desktop и поведение автоматической очистки.
- [x] Описать вариант с выделенным внешним PostgreSQL через PowerShell `$env:TEST_DATABASE_URL=...` и Bash `export TEST_DATABASE_URL=...`.
- [x] Указать, что `DATABASE_URL` из `.env` игнорируется специально, а production URL нельзя задавать для тестов.
- [x] Добавить страницу в таблицу навигации документации и обновить актуальные инструкции с тестовыми командами.
- [ ] Выполнить полный набор при доступном PostgreSQL; здесь Docker daemon недоступен. Остальные проверки проходят.
