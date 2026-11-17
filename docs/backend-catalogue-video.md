# Публичный каталог и видео туров

Изменения подготовлены в ветке `fix/backend-review-20261107`, исходный коммит
`5675a9a`, исходный Alembic head `20261107_0027`. На рабочий сервер ничего
не выкладывалось. Клиентский фронтенд не изменялся.

## Публичное чтение

GET списков и деталей туров, отелей, транспорта, треккинга и вертолётных туров,
их фотографий и программ доступен без Authorization. Неактивные и отсутствующие
объекты возвращают 404; коллекции с фильтром по неактивному/отсутствующему
родителю также возвращают 404. Общие коллекции исключают скрытые данные.

Авторизация чата HTTP/WebSocket, проверка владельца сессии, личные данные,
заявки, административные операции и права на отзывы сохранены.

## Видео

`TourVideo`: `id`, `tour_id`, `video_url`, необязательный `poster_url`, `order`.
Связь с туром каскадная, порядок — `(order, id)`. Ссылки хранятся в PostgreSQL,
файлы — в `MEDIA_ROOT/videos/YYYY/MM/`. Существующие изображения и `main_image`
сохранены. `TourDetailSchema.videos` возвращает `[]` при отсутствии видео;
коллекция загружается через `selectinload` с постоянным количеством запросов.

Маршруты:

* `GET /tour-videos/?tour_id=42`, `GET /tour-videos/7/` — публично для активных туров.
* SQLAdmin: представление `TourVideoAdmin`, создание/изменение/удаление связей.
* `POST /admin/media/video-upload` — загрузка с сессионной cookie SQLAdmin, роль
  owner/catalog_editor. Полученный URL вставляется в поле `video_url` формы SQLAdmin.

Файл разбирается `ffprobe` с ограниченными протоколами и демультиплексорами,
проверяется наличие видеопотока и контейнер MP4/WebM. Для WebM проверяются
также допустимые кодеки. Имя/расширение/Content-Type клиента не определяют
результат. Видео не передаётся Pillow и не перекодируется; совместимость
конкретного MP4-кодека с браузером зависит от самого файла.

Multipart использует дисковый spooling Starlette; тело запроса ограничивается
middleware при чтении, включая запросы без Content-Length. При сохранении
данные копируются блоками по 1 MiB, проверяется отдельный лимит файла.
Временный файл удаляется при ошибке. Имена — UUID, расширение определяется
после проверки. Неверный формат даёт 400, превышение размера — 413,
отсутствующий ffprobe — 503. Проверка ffprobe ограничена 30 секундами.

Новые настройки:

```dotenv
MAX_VIDEO_UPLOAD_BYTES=104857600
FFPROBE_BINARY=ffprobe
```

Лимит по умолчанию 100 MiB, допустимо 1..1073741824 байт. Для multipart
middleware допускает дополнительно 64 KiB служебных данных; сам файл обязан
укладываться в MAX_VIDEO_UPLOAD_BYTES. Существующий REQUEST_BODY_TIMEOUT
(по умолчанию 10 секунд, максимум 60) применяется к получению загрузки.
Для медленных соединений его можно увеличить. Общий MAX_REQUEST_BODY_BYTES
не ограничивает специально выделенные маршруты загрузки видео.

На сервере нужен ffprobe в PATH или по FFPROBE_BINARY; Dockerfile и CI
устанавливают ffmpeg (включает ffprobe). Это изменение ещё не развёрнуто.
В Caddyfile нет отдельного ограничения тела, запросы идут к middleware API.
Существующий Caddy file_server обслуживает `/media/` с типами MP4/WebM и Range;
локальный Starlette StaticFiles проверен запросами Range: ответ 206,
Content-Range и корректные байты. Сам Caddy в этой среде не запускался.
При наличии дополнительного внешнего прокси его ограничения надо согласовать
с лимитом API при будущем развёртывании.

## Вход администратора

В исходной ветке коммитов `bfc7dd3`/`48949f6` и миграции
`20261108_0029_remove_admin_mfa.py` не было. Убраны вызовы второго фактора
в API/SQLAdmin, поле TOTP в серверной схеме и форме SQLAdmin, проверки
`admin_mfa` в доступе к SQLAdmin и уведомлениям. `create_admin.py` больше
не требует настройки Authenticator. Старый ADMIN_MFA_REQUIRED не действует.

Пароли, ограничения входа, активность администратора, роли, access/refresh,
ротация и отзыв сессий сохранены. Поддержка существующего remember_device
оставлена для совместимости, но токен устройства не заменяет пароль и не
требуется для входа. Исторические поля MFA, данные и миграции сохранены;
повторной миграции удаления колонок нет, поскольку для нового поведения
изменение схемы admins не требуется. Старые утилиты MFA не участвуют во входе.
Восстановление пароля и подтверждение email клиента не изменялись.

Если клиентский фронтенд сам показывает регистрацию или поле MFA, это
остаётся ограничением интерфейса. Изменения API эти окна автоматически
не убирают.

## Миграция

Новая миграция `20261109_0028_tour_videos.py` продолжает фактический
head `20261107_0027` и создаёт только таблицу и индекс видео.
Существующие миграции и данные не изменяются.

После обычного резервного копирования, в нужном окружении:

```sh
python -m alembic current
python -m alembic heads
python -m alembic upgrade head
```

Проверено на отдельной временной PostgreSQL 17: upgrade от предыдущего head,
сохранение существующего тура/main_image, добавление видео, downgrade до
предыдущего head, повторный upgrade. Downgrade удаляет новую таблицу видео;
для рабочей базы его без необходимости выполнять не следует.

## Пример ответа

Гость: `GET /tours/42/` содержит прежние поля и
`"videos":[{"id":7,"tour_id":42,"video_url":"/media/videos/2026/11/0123456789abcdef0123456789abcdef.mp4","poster_url":null,"order":0}]`.
Для активного тура без видео — `"videos":[]`.

Удаление связи в SQLAdmin не удаляет общий медиафайл с диска:
тот же URL может использоваться другими записями.

## Проверки

Итоговый полный прогон на отдельной временной PostgreSQL 17:
**692 passed, 16 skipped**. Пропущены opt-in проверки с обращением к Gemini.
Дополнительный прогон после регистрации отдельных роутеров: **81 passed**.
Проверки миграции выполнялись на отдельной случайной тестовой базе.

```powershell
$env:TEST_DATABASE_URL = 'postgresql+psycopg2://postgres@127.0.0.1:55439/postgres'
$env:FFPROBE_BINARY = 'C:/path/to/ffprobe.exe'
python -m pytest -q --basetemp=.test-tmp-final
```

Адрес выше относится только к использованному временному экземпляру тестов;
он остановлен после проверки. Для повторения нужен свой тестовый PostgreSQL
с правом CREATEDB. Тестовая инфраструктура создаёт случайные базы
`test_kyrgyzgo_*` и удаляет их после тестов.

Пройдены Ruff, `scripts.format_code --check`, compileall; Bandit для новых
роутеров не нашёл проблем среднего или высокого уровня. Проверены гостевые
детали всех пяти типов каталога, 404 скрытых родителей/вложенных объектов,
авторизация HTTP/WebSocket и владелец чата, права административных операций
и отзывов, регистрация/вход клиента, вход администратора без MFA и неверный
пароль, сессии/refresh/отзыв, реальные MP4/WebM, CRUD связей и `videos`,
постоянное число SELECT, Content-Type/Range, неверный формат/размер,
загрузка без Content-Length, очистка временных файлов и прежняя загрузка фото.

## Изменённые файлы

* `.env.example`
* `.github/workflows/ci.yml`
* `Dockerfile`
* `alembic/versions/20261109_0028_tour_videos.py`
* `create_admin.py`
* `docs/backend-catalogue-video.md`
* `main.py`
* `mysite/admin/authentication.py`
* `mysite/admin/realtime.py`
* `mysite/admin/setup.py`
* `mysite/admin/templates/sqladmin/login.html`
* `mysite/admin/views.py`
* `mysite/api/admin.py`
* `mysite/api/admin_access.py`
* `mysite/api/admin_sessions.py`
* `mysite/api/helicopter_image.py`
* `mysite/api/helicopter_tour.py`
* `mysite/api/hotel.py`
* `mysite/api/hotel_image.py`
* `mysite/api/resource_limits.py`
* `mysite/api/tour.py`
* `mysite/api/tour_image.py`
* `mysite/api/tour_program.py`
* `mysite/api/tour_video.py`
* `mysite/api/transport.py`
* `mysite/api/transport_image.py`
* `mysite/api/trekking.py`
* `mysite/api/trekking_image.py`
* `mysite/api/trekking_program.py`
* `mysite/api/video_media.py`
* `mysite/database/models.py`
* `mysite/database/schemas/admin.py`
* `mysite/database/schemas/catalogue.py`
* `mysite/database/storage_validation.py`
* `tests/conftest.py`
* `tests/fixtures/video.mp4`
* `tests/fixtures/video.webm`
* `tests/test_admin_mfa_roles.py`
* `tests/test_admin_security_sessions.py`
* `tests/test_api_permission_matrix.py`
* `tests/test_api_smoke.py`
* `tests/test_catalogue_chat_boundary.py`
* `tests/test_main_regressions.py`
* `tests/test_public_catalogue_video.py`
* `tests/test_shared_client_access.py`
* `tests/test_tour_video_migration.py`
* `tests/test_user_flow_regressions.py`
