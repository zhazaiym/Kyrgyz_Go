# Документация Kerben Travel

Актуальность навигации: 7 ноября 2026. Основное описание проекта находится в [корневом README](../README.md). Исторические отчёты ревью и планы удалены из рабочего дерева и доступны в истории Git.

| Что нужно узнать | Документ |
| --- | --- |
| Быстрый обзор проекта и локальный запуск | [README](../README.md) |
| Пакет ML, ошибки Gemini, тесты и миграция чата | [ML](../ML/README.md) |
| HTTP/WS API, авторизация, схемы и ошибки | [API](../API.md) |
| Карта модулей и проверки изменений | [Архитектура](architecture.md) |
| Локальный запуск тестов с изолированной PostgreSQL | [Локальные тесты](local-testing.md) |
| Параметры сервера и ограничения развёртывания | [DEPLOY](../DEPLOY.md) |
| Как обновляется прод и правила перед мержем в main | [DEPLOY](../DEPLOY.md#как-обновляется-прод) |
| PostgreSQL и переход со старой базы | [Миграция PostgreSQL](postgresql-migration.md) |
| Общий аккаунт сайта и чата | [Авторизация клиента](shared-client-auth.md) |
| Поведение чата, бюджеты и источники фактов | [Эффективность чата](chat-efficiency.md) |
| Форматирование Python и проверки CI | [Стиль кода](code-style.md) |
| Гостевой AI-подбор без входа | [Гостевой AI](guest-ai.md) |
| Публичный каталог и видео туров | [Каталог и видео](backend-catalogue-video.md) |
| Импорт и цены Trekking | [Импорт Trekking](trekking-import.md), [Цены](trekking-pricing.md) |

GitHub workflow только проверяет код; прод обновляет себя сам из `main` после зелёного CI (см. DEPLOY.md). `KYRGYZGO` остаётся в исходниках и runtime-идентификаторах ради совместимости; актуальное название продукта в руководствах — Kerben Travel.


Current operations: the [API reference](../API.md) covers admin login and `/metrics`; [deployment guidance](../DEPLOY.md) describes admin sessions and translation retry; the local load smoke is `python -m scripts.load_test` and uses a disposable PostgreSQL database with Gemini stubbed by default.
