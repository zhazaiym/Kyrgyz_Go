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

Verification completed on 2026-10-28:

- `TEST_DATABASE_URL=postgresql+psycopg2://postgres@127.0.0.1:5432/postgres python -m pytest -q`: **456 passed in 163.33s**. The test helper created and dropped its own temporary PostgreSQL database.
- Ruff lint on the changed Python files: **passed**.
- Ruff format check on the changed Python files: **17 files already formatted**.
- `git diff --check`: **passed**.

Migrations 0014 through 0016 must be manually applied before deploying this code because the deployment workflow blocks automatic schema changes.

---

## Follow-up for review `bbab808..worktree` (2026-10-28)

### Required block A

- **A1′ — implemented:** SQLAdmin no longer treats absent languages/fields in the submitted JSON as deletion. The update hook locks and refreshes the record, merges explicit edits into the latest translations, and queues a fresh translation for explicit empty values. Test through the real SQLAdmin edit GET/POST path: `test_sqladmin_form_preserves_worker_translations_and_explicit_clear_requeues` (form opened with `{}`, worker writes translations, submit preserves them; explicit clear queues regeneration).
- **A4 — implemented:** migration 0015 keeps a database server default `scope=''`, matching the ORM default, so old containers can insert counters without naming `scope`. Tested by `test_translation_migration_downgrade_removes_stale_values`, which upgrades and issues the legacy INSERT.
- **A5 — implemented:** unknown login identifiers are SHA-256 hashed before storing the limiter account index; known accounts still use their numeric account ID. `test_unknown_254_character_email_is_not_stored_as_rate_limit_identity` verifies HTTP 401 for a 254-character email and confirms the raw value is absent from `account_id`.
- **A6 — data branches removed; `master` retained active by owner decision:** after repository-owner authorization, deleted `improve-chat-consultation-20261027` and `jazi`, which each contained four `kyrgyzgo_*.db` files. The owner confirmed that `master` will continue to be used, so it remains available and has no abandonment marker; `ABANDONED.md` was removed in commit `9bf4027`. The active remote branches (`main` and `master`) contain no `.db` files. GitHub Support has not been contacted to purge cached historical objects; that external request remains separate.

### Required block B

- **B4 — implemented:** runtime tour display now uses `translation_ready`; SQL search and ordering apply equivalent hash and non-whitespace checks. Test: `test_tour_display_and_search_fall_back_for_whitespace_translation`.
- **B5 — implemented:** see B7 below; explicitly clearing a translation schedules immediate regeneration.
- **B6 — implemented:** whitespace-only tour translations now fall back in detail/list display, and SQL search/sort uses the same non-whitespace rule. Test: `test_tour_display_and_search_fall_back_for_whitespace_translation`.
- **B7 — implemented:** explicit empty SQLAdmin translation fields are removed from stored translations/manual overrides and enqueue a replacement. Test: `test_sqladmin_form_preserves_worker_translations_and_explicit_clear_requeues`.
- **B9 — implemented:** invalid or empty `ADMIN_ALLOWED_IPS` logs an error and denies `/admin` only; public paths continue. IPv4-mapped IPv6 addresses are normalized with `client_network`. Tests: `test_invalid_admin_allowlist_fails_closed_without_disabling_public_paths`, `test_admin_allowlist_normalizes_ipv4_mapped_ipv6`.
- **B10 — implemented:** deployment checks the production `.env` for a non-empty, valid `ADMIN_ALLOWED_IPS`; `DEPLOY.md` documents the SSH tunnel/Docker gateway address issue. Tests: `test_deploy_requires_explicit_valid_admin_allowlist`, `test_environment_example_documents_required_settings`.
- **Restored admin login limiter coverage:** `test_admin_login_limit_caps_attempts_per_account_and_ip` verifies five failed attempts are accepted and the sixth from the same account/IP is rate-limited.
- **Legacy CRLF rows — implemented:** migration 0016 normalizes localized source fields and updates hashes only when the stored hash matched the pre-migration source. SQLAdmin also normalizes existing and submitted values before compare/save. Test: `test_translation_migration_downgrade_removes_stale_values`.

### Optional block C

- **C8 — implemented:** migration 0014 downgrade clears stale tour translation fields instead of copying Russian source text into translation columns. The migration regression test now expects the legacy non-null title to be empty.
- **C11 — implemented:** admin allowlist uses the shared `client_network` identity; see `test_admin_allowlist_normalizes_ipv4_mapped_ipv6`.
- **C12 — implemented:** the Alembic parser maps legacy `version_path_separator = space` and `newline` to their actual separators. Test: `test_candidate_schema_supports_legacy_named_version_path_separator`.
- **C14 — deferred:** query optimization is independent of these correctness and deployment blockers; retain the existing query plan until separately benchmarked.
- **C15 — deferred:** helper/constant deduplication is cleanup and is not needed for the requested fixes.
- **C16 — already implemented in `bbab808`:** `build_preview()` separates internal completeness from stage-aware `can_confirm`.

Verification completed on 2026-10-28:

- `TEST_DATABASE_URL=postgresql+psycopg2://postgres@127.0.0.1:5432/postgres python -m pytest -q`: **468 passed in 162.45s**. Tests created and dropped a temporary PostgreSQL database.
- `ruff check .`: **passed**.
- `ruff format --check` on the 18 changed Python files: **passed**.
- `git diff --check`: **passed**.

Migrations 0014 through 0016 require the existing manual deployment procedure before this application version is deployed.

---

## Follow-up for review `0871c18..worktree` (2026-10-28)

### Required block A

- **A7 — implemented:** migration 0016 now updates `tours.<field>` directly, normalizes every tour row containing CR (including tours without translation rows), and updates a translation hash only when it matched the old raw source hash. `test_translation_migration_downgrade_removes_stale_values` covers a tour with CRLF in title/description and a matching translation hash, plus a tour without translations; it verifies normalized source and a still-ready English translation.
- **A8 — implemented:** `source_field_hash()` and the SQL hash expression normalize CRLF and lone CR to LF. REST writes that only change line endings therefore keep translations valid without enqueueing a replacement. Test: `test_tour_rest_put_only_normalizing_line_endings_keeps_translation` (PUT and localized GET); `test_translation_readiness_uses_same_whitespace_and_source_rules` checks equal hashes.

### Required block B

- **B4 — implemented:** SQL filtering now removes all POSIX whitespace before testing a translation, matching Python `str.strip()`. Test: `test_tour_display_and_search_fall_back_for_whitespace_translation` uses newline/tab content and checks SQL search and display fallback.
- **B5 — implemented:** deployment rejects `0.0.0.0/0` and `::/0`. Test: `test_deploy_requires_explicit_valid_admin_allowlist`.
- **B6 — implemented:** `.env` parsing uses the last assignment and strips unquoted or quoted trailing comments. Tests: `test_deploy_requires_explicit_valid_admin_allowlist` covers repeated assignments, inline comments, quotes, and a final empty assignment.
- **B7 — implemented:** the SQLAdmin explicit-clear test spies on `enqueue_translation`, verifies exactly one enqueue, and confirms only the cleared translation is removed from stored JSON. Test: `test_sqladmin_form_preserves_worker_translations_and_explicit_clear_requeues`.
- **B8 — implemented:** migration test includes tour source fields and verifies translated readiness after upgrade, as listed for A7.
- **B13 — implemented:** `.env.example` leaves `ADMIN_ALLOWED_IPS` blank and explains explicit local/production setup. Test: `test_environment_example_documents_required_settings`.

### Optional block C

- **C3 — partially addressed:** the required empty-form/worker-write case is covered by `test_sqladmin_form_preserves_worker_translations_and_explicit_clear_requeues`; a render-time baseline for a form that already displayed translations is not implemented, so a later worker update can still race with an edited stale value.
- **C9 — not implemented:** absent JSON keys remain no-ops to protect worker updates; admins can clear a field by setting it to an empty string, which is covered by the SQLAdmin integration test.
- **C10 — implemented:** whitespace-only manual translations follow the same explicit-clear path as refresh detection. Test: `test_whitespace_manual_translation_is_treated_as_explicit_clear`.
- **C11 — not implemented:** clearing one field still regenerates the record's full translation set; selective-field job support is deferred to avoid changing the shared worker contract in this blocker cycle.
- **C12 — not implemented:** simultaneous source and manual-translation edits lack a trusted render-time baseline; this remains grouped with C3 for a dedicated SQLAdmin form-state change.
- **C14 — implemented:** native IPv6 `/64` allowlist behavior is covered by `test_admin_allowlist_accepts_native_ipv6_network_identity`.
- **C15 — implemented:** migration 0016 scans only localized rows whose source fields contain CR.
- **C16 — implemented:** the unknown-email test verifies a successful hashed account index and checks that no stored account key begins with the raw identifier prefix; test: `test_unknown_254_character_email_is_not_stored_as_rate_limit_identity`.
- **C17 — not implemented:** `shlex.split` is retained for legacy `space` separators so quoted version paths containing spaces remain supported.
- **C18 — implemented:** account index extraction now splits at the final `:ip:` boundary; test: `test_account_index_parses_principal_from_the_last_address_delimiter`.

The active `master` branch is intentionally retained and synchronized to `main` by merge commits so both branches keep their histories and code trees match. GitHub Support has not been contacted about cached historical database objects.

Verification completed on 2026-10-28:

- `TEST_DATABASE_URL=postgresql+psycopg2://postgres@127.0.0.1:5432/postgres python -m pytest -q`: **477 passed in 163.36s**. Tests created and dropped a temporary PostgreSQL database.
- `ruff check .`: **passed**.
- `ruff format --check` on the 12 changed Python files: **passed**.
- `git diff --check`: **passed**.

Migrations 0014 through 0016 require the documented manual application before this release is deployed. A request to GitHub Support for cache removal has not been sent.

---

## Цикл 8: follow-up к `edefb05` (2026-10-28)

База: `edefb05dbcf30b9d0407fcbb03c126ec961edc5d`, ветка `main`.
Диапазон проверки: `edefb05..HEAD` после фиксации follow-up. Публикация в main
выполняется по отдельному поручению пользователя после успешных проверок.
Проверено последнее заключение: «ПРИНЯТО С ЗАМЕЧАНИЯМИ». Блок A и принятые
A1-A8 не открываются повторно. Нумерация ниже соответствует находкам **цикла 8**.

| Находка | Статус и реализация | Подтверждающие тесты |
| --- | --- | --- |
| 1 | Исправлено. SQL проверяет непустой перевод через `btrim` с явным набором всех 29 пробельных символов Python `str.strip()`. Правило не зависит от локали PostgreSQL. Оно общее для туров и JSON-переводов, поиска и сортировки. | `test_sql_whitespace_matches_python_strip_independent_of_locale`; `test_tour_display_and_search_fall_back_for_whitespace_translation` (ASCII, U+00A0, U+2007, U+202F, U+0085, U+3000, U+2028, U+001C). |
| 2 | Исправлено вместе с 6. Самописный парсер `.env` удалён; deploy валидирует `services.api.environment.ADMIN_ALLOWED_IPS` из настоящего `docker compose config --format json`. Последний `export`, комментарии и Compose overrides учитывает сам Compose. | `test_deploy_validates_effective_compose_admin_policy`. |
| 3 | Исправлено. Отклоняются сети шире IPv4 /16 и IPv6 /32, включая /0, обе /1, IPv6 2000::/3. Это верхняя граница допуска, а не рекомендация разрешать столь большие сети. Для админов по-прежнему нужны конкретные адреса/VPN. | `test_deploy_requires_explicit_valid_admin_allowlist`; `test_deploy_validates_effective_compose_admin_policy`. |
| 4 | Исправлено. Проверка ищет префикс `unknown:` + начало исходного email; ожидаемый полный SHA-256 account_id также проверяется. | `test_unknown_254_character_email_is_not_stored_as_rate_limit_identity`. |
| 5 | Исправлено. Оба варианта `space`, современный и legacy, используют буквальный `split(' ')`, без shlex. Апостроф в имени каталога не интерпретируется как кавычка. | `test_candidate_schema_space_separator_keeps_apostrophes_literal`; `test_candidate_schema_supports_legacy_named_version_path_separator`. |
| 6 | Исправлено как корневая причина 2 и 8. Перед любым build/backup/активацией deploy проверяет эффективную среду API. Валидация не выводит JSON со значениями секретов. | `test_deploy_validates_effective_compose_admin_policy`; `test_deployment_failure_never_activates_a_new_schema_and_restores_exact_override` использует mock итогового Compose JSON. |
| 7 | Исправлено. Из admin middleware удалена избыточная ветка `identity_network/subnet_of`. IPv4-mapped IPv6 продолжает нормализоваться через `client_network`; для native IPv6 проверяется фактический адрес в сети. | `test_admin_allowlist_normalizes_ipv4_mapped_ipv6`; `test_admin_allowlist_accepts_native_ipv6_network_identity`. |
| 8 | Исправлено. Тест сравнивает конкретную победившую сеть, а при отказе конкретную причину. Настоящий Compose читает `ADMIN_ALLOWED_IPS= # cleared` как непустую строку `# cleared`, поэтому ожидается ошибка `invalid IP or network`, а не `must set`. Отдельный случай настоящего пустого присваивания проверяет `must set`. | `test_deploy_validates_effective_compose_admin_policy`. |
| 9 | Исправлено. В `.env.example` присваивание закомментировано: копирование примера сохраняет localhost fallback. Явная пустая строка по-прежнему закрывает админку; deploy требует явной эффективной настройки. | `test_environment_example_keeps_local_admin_fallback`; `test_environment_example_documents_required_settings`. |
| 10 | Документировано. В `DEPLOY.md` запрещены REST/SQLAdmin-правки каталога между миграциями и активацией соответствующего образа. Это процедура обслуживания, а не новая миграция или фоновый пересчёт данных. | Автоматического теста организационного запрета нет. В этом цикле рабочая БД не мигрировалась, релиз не активировался. |
| 11 | Исправлено. Downgrade 0014 принимает совпадение как с исходным сырым хешем 0014, так и с нормализованным хешем новых версий. Upgrade 0014 сохраняет замороженный прежний алгоритм. Актуальные CRLF-переводы сохраняются, устаревшие очищаются. Код приложения миграция не импортирует. | `test_translation_migrations_preserve_current_normalized_hashes_and_leave_stale_hashes`; `test_translation_migration_downgrade_removes_stale_values`. |
| 12 | Исправлено. Пустое/пробельное явно переданное поле очищается вместе с хешем и manual-флагом даже при совпадении с уже сохранёнными пробелами. Сравнение формы замечает такую очистку; после удаления повторное сохранение не ставит ту же задачу вновь. | `test_sqladmin_saved_whitespace_translation_is_cleared_and_enqueued_only_once` через реальные GET/POST SQLAdmin со spy enqueue; `test_whitespace_manual_translation_is_treated_as_explicit_clear`. |
| 13 | Исправлено. Добавлен реальный migration-тест с en/de, CRLF, одиночным CR, CR-CRLF и четырьмя полями тура. Текущие сырые хеши обновляются, устаревший de.title сохраняет старый хеш и остаётся неготовым. Тот же тест проверяет downgrade после записи CRLF новым приложением. | `test_translation_migrations_preserve_current_normalized_hashes_and_leave_stale_hashes`. |
| 14 | Частично исправлено. Выборка переводов туров в 0016 ограничена исходниками с CR. SQL больше не делает regexp_replace; используется btrim с точным Unicode-набором. Коррелированные подзапросы не переписывались без сравнительного benchmark. | `test_translation_migrations_preserve_current_normalized_hashes_and_leave_stale_hashes`; `test_sql_whitespace_matches_python_strip_independent_of_locale`. |

Дополнение к тестовому окружению: `test_rendered_compose_reserves_separate_api_and_caddy_addresses`
теперь игнорирует унаследованный `COMPOSE_FILE`, чтобы проверять свой fixture,
а не чужую конфигурацию машины. Docker CLI и Compose подключены к тестовому
контейнеру без Docker socket; проверки рендеринга действительно выполнялись,
а не пропускались.

### Принятые отложенные пункты

- C3: render-time baseline SQLAdmin отложен как отдельное изменение формы. Непроверенный локальный черновик, начатый до получения цикла 8, сохранён в `/tmp/kyrgyzgo-deferred-form-baseline.patch` и не включён в итоговые изменения.
- C9: отсутствие JSON-ключа остаётся no-op для сохранности переводов worker. Очистка через пустую строку работает и описана в `API.md`; отдельной подсказки внутри SQLAdmin пока нет.
- C11: выборочная регенерация одного поля/языка отложена, поскольку меняет контракт общих задач перевода.
- C12: одновременное изменение исходника и ручного перевода требует доверенного состояния открытой формы, рассматривается вместе с C3.
- GitHub cache removal: открыт. Запрос в GitHub Support не отправлялся: отправка внешнего обращения от имени владельца не поручена. Удаление веток и синхронизация main/master уже приняты; заново они не выполнялись.

### Проверки этого цикла

Изолированный контейнер с рабочей копией исходников, временные базы `test_kyrgyzgo_*`.
Использовались синтетические Gemini/SECRET_KEY, внешние AI-вызовы тестами отключены.
Рабочие таблицы PostgreSQL тестами не очищались и не мигрировались.

```text
ruff check .
All checks passed!

pytest -q -ra
502 passed in 157.72s (0:02:37)
```

Первый целевой прогон выявил два неверных тестовых ожидания: `# cleared`
в Compose и унаследованный COMPOSE_FILE. Они исправлены; итоговый полный
прогон выше зелёный, без skip. Ruff-format/isort применены только к связанным
изменённым файлам. `git diff --check` проходит.

### Условия проверки уже работающего edefb05

В этом цикле деплоя, изменения production `.env`, рестартов и миграций не было.
Работающий ранее установленный образ остаётся `kyrgyzgo-api:main-edefb05`.
Из предыдущего bootstrap `.env` сохранён без изменений; эффективный
`ADMIN_ALLOWED_IPS=127.0.0.1/32,::1/128` задан в отдельном Compose override,
а не добавлен в `.env`. Доступ с произвольного публичного адреса не открыт.

Проверки по условию 4 проведены на работающем сервере:

- Публичный `GET /admin/`: 403.
- Loopback из allowlist: `/admin/` перенаправляет на вход, `GET /admin/login`: 200.
- Карточка существующего тестового тура с клиентским токеном на `lang=en`: 200 и английский `TEST:` title.
- `GET /faqs/?lang=en`: 200 и английский текст.
- `GET /tours/?lang=en&search=<английское название>`: 200 и нужный id в выдаче.

Проверка входа создала временный login token и затем отозвала его; каталог,
заявки и существующие учётные данные не изменялись. Новые правки цикла 8
предназначены для публикации в main; на работающий сервер в этом цикле они не устанавливались.

### Документация для фронтенда

Добавлен `API.md`: 137 операций текущего OpenAPI, 91 JSON-схема, скрытые
совместимые/снятые маршруты, HTTP/WS авторизация, стадии чата, revision,
подтверждение заявки, ошибки, фильтры и пагинация. Документ сопоставлен
с OpenAPI и кодом динамических ответов. Длинные тире в нём отсутствуют.

---

## Цикл 10: follow-up по 93b3484 (2026-10-28)

Автодеплой намеренно удалён по решению владельца: GitHub Actions только проверяет код и запускает тесты. Сервер остаётся на ручном релизе; GitHub workflow не запускает production-деплой.

### Статусы замечаний

| Пункт | Статус | Проверка / примечание |
| --- | --- | --- |
| Цикл 9, находка 3: опасные IPv6 allowlist | Исправлено: отклоняются Teredo, NAT64, 6to4 и IPv4-mapped IPv6 сети. | `test_deploy_rejects_ipv6_transition_and_translation_allowlists` |
| Цикл 9, находка 4: Compose activation test | Исправлено: добавлен тест с реальным Docker Compose CLI и fixture-override; он проверяет сохранение allowlist после записи нового override. | `test_activation_override_preserves_allowlist_with_real_compose_cli` |
| Цикл 9, находка 5: stale empty SQLAdmin translation | Исправлено: очистка из устаревшей формы сохраняет более новый перевод, пришедший от worker после открытия формы. | `test_sqladmin_stale_empty_translation_does_not_erase_concurrent_worker_update`; `test_sqladmin_saved_whitespace_translation_is_cleared_and_enqueued_only_once` |
| Цикл 9, находка 6: WebSocket 403 | Исправлена документация: разделены HTTP 403 на рукопожатии и принятый сокет с `session_not_found`/close 1008. | ручное сопоставление `API.md` с `chat_ws.py` |
| Цикл 9, находка 7: лимиты чата | Исправлена документация: лимиты обозначены константами, добавлен лимит рукопожатий WebSocket. | ручное сопоставление `API.md` с кодом лимитера |
| Цикл 9, находка 8: `booking_needs_update` | Исправлена документация: описаны пропавшие/невалидные данные и ссылка на `missing_fields`. | ручное сопоставление `API.md` с ответами preview/confirm |
| Цикл 10, замечание 2: источник `ADMIN_ALLOWED_IPS` | Исправлено в `DEPLOY.md`: после установки generated override является источником истины; править allowlist нужно в нём. | документация |
| Цикл 10, замечание 3: GitHub deploy secrets и старый CI key | Не выполнено: требуется удалить секреты из GitHub Settings и проверить `authorized_keys` на сервере. В этом окружении нет доступа к этим настройкам; удалять ключи вслепую небезопасно. | внешнее действие владельца |
| Цикл 10, замечание 4: устаревший документ автодеплоя | Исправлено: `docs/automatic-deployment.md` удалён. | проверка дерева файлов |
| Цикл 10, замечание 5: статический адрес в health-check и документах | Отложено: server endpoint и SSH host key остаются параметрами текущей ручной инфраструктуры; API-документация больше не вшивает публичный IP. | изменить при переносе endpoint/сервера |
| A10: реальный доступ администратора | Не подтверждено и пока не настроено: владелец пока не знает фиксированный публичный IP/VPN egress. Не открывать allowlist на весь интернет; пока сохраняется deny-by-default. | нужен фиксированный IP или VPN; live `/admin/login` не проверялся |
| Условие ручного релиза: обновление доверенной серверной копии `ci_deploy.py` до `93b3484` или новее | Не подтверждено: root-доступа к production-серверу в этой сессии нет. | выполнить на сервере перед следующим релизом |
| GitHub cache removal для исторических `*.db` | Открыто для владельца; запрос в поддержку не отправлялся. | внешнее действие владельца |

### Проверки этого follow-up

Полный прогон выполнен на локальной тестовой PostgreSQL, тесты использовали временные `test_kyrgyzgo_*` базы и удалили их после завершения. Финальная команда:

```text
pytest -q
514 passed in 90.96s
```

`ruff check` на изменённых Python-файлах: `All checks passed!`.
`git diff --check`: без ошибок.
Форматирование сохранено в принятом соседним кодом стиле; `ruff format` к целым файлам не применялся.
