# Локальный запуск тестов

Полный набор тестов использует PostgreSQL и создаёт отдельную временную базу с именем `test_kyrgyzgo_<случайный идентификатор>`. После завершения эта база удаляется.

## Рекомендуемый запуск

Нужны Python 3.12, установленные зависимости разработки (`python -m pip install -r requirements-dev.txt`) и Docker Desktop с Docker Compose v2.17 или новее. Версия pytest закреплена в `requirements-dev.txt` и одинакова для локального запуска и CI.

Из корня проекта выполните:

```powershell
python -m scripts.run_tests
```

Запускатель поднимет временный PostgreSQL 17 на `127.0.0.1:55432`, дождётся готовности, выполнит `pytest`, затем удалит созданный Compose-контейнер. База не сохраняется в постоянном Docker volume. Если порт занят, задайте свободный порт перед запуском:

```powershell
$env:TEST_POSTGRES_PORT = '55433'
python -m scripts.run_tests
Remove-Item Env:TEST_POSTGRES_PORT
```

В Bash:

```bash
TEST_POSTGRES_PORT=55433 python -m scripts.run_tests
```

Можно передать аргументы pytest, например:

```powershell
python -m scripts.run_tests tests/test_tour_reviews.py -q
```

Unit-тесты самого тестового запуска без PostgreSQL и Docker:

```powershell
python -B -m pytest --confcutdir=tests/unit tests/unit -q
```

## Выделенный PostgreSQL

Если Docker недоступен, можно задать адрес отдельного тестового PostgreSQL с правом `CREATEDB`:

```powershell
$env:TEST_DATABASE_URL = 'postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/postgres'
python -m scripts.run_tests
Remove-Item Env:TEST_DATABASE_URL
```

В Bash:

```bash
TEST_DATABASE_URL='postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/postgres' \
  python -m scripts.run_tests
```

Подключение должно вести к выделенному тестовому серверу, а не к production. Тестовая фикстура создаёт и удаляет на нём случайную базу с префиксом `test_kyrgyzgo_`.

Без `TEST_DATABASE_URL` тесты не читают `DATABASE_URL` и `.env`. Это сделано намеренно, чтобы тестовый запуск не подключился к базе приложения по умолчанию. GitHub Actions использует свой PostgreSQL service и запускает тот же `python -m scripts.run_tests`.
