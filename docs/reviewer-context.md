# Контекст для следующего ревьюера

**Снимок для ревью:** коммит `d584852` (`Fix login and translation review findings`).  
**До изменений:** `25324f7`.  
**Ветки:** изменения опубликованы в `main` и `master`.

Этот документ объясняет замысел последних изменений и спорные решения. Он не заменяет независимую проверку: пожалуйста, сверяйте выводы с реализацией, моделями, миграциями и вызовами по всему проекту.

## Что проверять в первую очередь

1. **Вход и защита от перебора** — `mysite/api/rate_limit.py`, `mysite/api/client_auth.py`, `mysite/api/admin.py`, `mysite/admin/setup.py`, `mysite/api/password_reset.py`.
   - Один атомарный PostgreSQL upsert увеличивает лимит по IP и по паре «аккаунт + IP».
   - Глобальную блокировку аккаунта убрали: атакующий не должен запереть владельца, который входит с другого IP.
   - IP и аккаунт/IP ограничивают попытки, включая успешные; успешный вход не сбрасывает счётчики и не добавляет временное «доверие» к адресу.
   - `authenticate_client` требует `Request`, чтобы новые вызовы не могли случайно обойти лимиты.
   - Argon2 выполняется без блокировки строки клиента; после проверки короткая блокировка повторно проверяет хеш пароля.
   - Сброс пароля удаляет счётчик текущей пары «аккаунт + IP» в той же транзакции.
   - **Остаточный риск:** большое число адресов может распределить перебор. Жёсткую блокировку аккаунта не вернули из-за риска отказа владельцу. Для более сильной защиты нужны MFA для админов и CAPTCHA или подтверждение email для клиентов. Проверьте, достаточно ли нынешних лимитов, особенно для admin login.

2. **Согласованность переводов** — `mysite/translations/source.py`, `content.py`, `jobs.py`, `mysite/api/filter_utils.py`, `mysite/api/tour.py`, `mysite/admin/views.py`, миграция `alembic/versions/20261028_0014_translation_source_identity.py`.
   - Раньше переводы очищались при изменении исходного текста, а затем очередь могла потерять задачу; также старый перевод мог завершиться после сохранения нового текста.
   - Теперь у каждого переведённого поля хранится хеш исходного значения. Перевод показывается только при совпадении хеша; при несовпадении пользователь видит актуальный исходный текст.
   - `None` и `''` нормализуются одинаково, чтобы SQLAdmin не считал пустое значение изменённым.
   - Перед платным вызовом провайдера и перед записью результата исходник сверяется повторно. Переводы с признаком ручного редактирования worker не перезаписывает.
   - Восстановление после перезапуска ищет отсутствующие и устаревшие переводы; `None` не считается готовым переводом.
   - Поиск и сортировка по локализованным полям используют те же хеши, что и сериализация ответа. Проверьте, что SQL-выражения совпадают с нормализацией Python для всех поддерживаемых значений.
   - **Production:** миграция 0014 меняет схему. Автодеплой намеренно не применяет новую ревизию сам; перед релизом миграцию нужно применить отдельно по процедуре проекта.
   - **Остаточный риск:** очередь остаётся локальной для процесса. После рестарта она восстанавливается сканированием. Если переводчик недоступен, пользователь увидит исходный текст; задача будет найдена при следующем восстановлении.

3. **Этап подтверждения чата** — `mysite/api/chat.py`, `mysite/api/chat_service.py`.
   - Внутренний `build_preview()` использует `can_confirm` как сигнал, что данных достаточно, чтобы перевести чат в `awaiting_confirmation`.
   - Публичный `/booking/preview` дополнительно проверяет этап, поэтому на `collecting` не предлагает подтверждение.
   - Не переносите stage-проверку внутрь `build_preview()`: это создаёт цикл, в котором чат не может перейти на этап подтверждения.

4. **Разбор схемы Alembic при деплое** — `scripts/ci_deploy.py`.
   - Добавлена поддержка старого разделителя-запятой и `pkg:dir`; для `version_locations` поддерживаются настройки из `alembic.ini`.
   - Проверки покрывают обычные пути, legacy comma и локальный package-relative `script_location`. Проверьте также edge cases конфигурации, чтобы проверка кандидата не пропустила миграцию или не объявила ложную голову.

## Проверки, выполненные автором изменений

- `pytest -q`: **447 passed**.
- `ruff check` на изменённых Python-файлах: успешно.
- `ruff format --check` на изменённых Python-файлах: успешно.
- `git diff --check`: успешно.
- Миграция 0014 применялась тестовой PostgreSQL-базой в полном прогоне.

## Как оставить находки

Для каждой находки укажите файл и строки, условия воспроизведения, влияние на пользователя/безопасность и почему существующая проверка не ловит проблему. Отделяйте подтверждённые дефекты от предположений. В первую очередь ищите ошибки в гонках и транзакционных границах, несовпадение поведения list/detail/search, обход лимитов через альтернативные API и обратную совместимость production-миграции.

Пожалуйста, также явно сообщите, если пункт из этого документа уже исправлен в последующем коммите: `d584852` — базовая точка этого контекста, а текущую ветку для ревью нужно проверять отдельно.

---

## Follow-up implementation for review `7a139dc..worktree` (2026-10-28)

The local checkout was already current with `origin/main` at `7a139dc`. This section records the uncommitted follow-up changes for the next review.

### Required block A

- **A1 — implemented:** SQLAdmin content saves now lock and refresh the row, compare translation edits against the form snapshot, and merge changes into the latest stored JSON. Only changed, current-source fields become manual. Stale source hashes remain stale. CRLF is normalized to LF. Regression coverage: `test_sqladmin_marks_only_changed_translation_field_as_manual`, `test_unchanged_stale_translation_form_does_not_refresh_its_hash`, `test_admin_merge_keeps_translation_written_after_form_was_loaded`, and `test_sqladmin_lf_and_crlf_source_are_equal_and_do_not_schedule_translation`.
- **A2 — implemented with allowlist:** `ADMIN_ALLOWED_IPS` gates `/admin` and `/admin/*` at the ASGI layer. An address outside the allowlist can make **0 accepted attempts/minute**. If all administrators use one allowlisted VPN egress, the existing admin login limiter allows at most **5 attempts/minute** from that egress. If all 100 addresses are mistakenly allowlisted, the remaining per-IP cap allows up to **500 attempts/minute** (5 × 100), so allowlisting must stay limited to the VPN/fixed admin egress. Configure only administrator VPN/fixed egress addresses. Test: `test_admin_paths_are_restricted_to_configured_networks`.
- **A3 — implemented:** migration 0014 now embeds its frozen field list and hash function, without importing application modules. Downgrade removes stale content translations and restores current source text for stale tour translations. Regression coverage: `test_translation_migration_downgrade_removes_stale_values`; the existing empty-database migration test also covers upgrade with `GEMINI_API_KEY` unset.

### Required block B

- **B1 — implemented:** stale manual translations are no longer treated as complete; display falls back to the source and recovery regenerates the stale field. Test: `test_stale_manual_field_falls_back_to_source_then_can_be_regenerated`.
- **B2 — implemented:** SQLAdmin source and translation strings normalize CRLF/CR to LF before compare and save. Test: `test_sqladmin_lf_and_crlf_source_are_equal_and_do_not_schedule_translation`.
- **B3 — implemented:** migration 0015 records limiter scope/account dimensions; password reset removes every client account/IP row plus matching in-process blocks. Test: `test_password_reset_cleanup_removes_all_account_ip_counters_and_blocks`.
- **B4 — implemented:** `translation_ready` is shared by public display and recovery, including whitespace-only values. Test: `test_translation_readiness_uses_same_whitespace_and_source_rules`.
- **B5 — implemented:** removing an unavailable optional service immediately emits a fresh summary and enters `awaiting_confirmation` when the remaining request is complete. Test: `test_button_confirmation_recovers_and_an_unavailable_optional_service_can_be_removed`; it also checks that preview in `collecting` does not offer confirmation.

### Optional block C

- **C3 and C9 — implemented for SQLAdmin content rows:** row lock/refresh plus snapshot merge prevents stale forms from overwriting translation-worker writes. Covered by `test_admin_merge_keeps_translation_written_after_form_was_loaded`. Other worker/tour races remain for separate review.
- **C7 — deferred:** migration 0014 backfills hashes for existing translations as the 28 October review permits; no second paid translation pass is scheduled.
- **C12 — unchanged:** the existing Alembic parser implementation is outside this change set.
- **C14 — deferred:** localized query optimization is unrelated to the required correctness/security fixes.
- **C15 — deferred:** helper/constant cleanup is unrelated to the required correctness/security fixes.
- **C16 — implemented with B5:** `build_preview()` returns internal `complete` separately from stage-aware public `can_confirm`.

Tests and lint were not run in this session. The project dependencies and the required isolated PostgreSQL test environment are not available here; the test names above describe added regression coverage, not executed results. Migrations 0014 and 0015 must be manually applied before deploying this code because the deployment workflow blocks automatic schema changes.
