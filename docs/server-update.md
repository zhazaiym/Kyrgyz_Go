# Обновление действующего сервера KYRGYZGO

## Текущий релиз: email и заявки только из чата

На сервере запущен `20261023-auth-chat-6c3844`, исходники находятся в
`/home/ubuntu/releases/20261023-auth-chat-6c3844`, образ —
`kyrgyzgo-api:release-20261023-auth-chat-6c3844`.
Установлен `email-validator`, применена миграция `20261023_0004`.
Существующие аккаунты сохранены; вход доступен по логину или email.
Прямые POST-заявки вне чата отключены, в админке оставлен раздел «Заявки из чата».

Резервная копия перед этим обновлением:
`/home/ubuntu/kyrgyzgo-backups/20261023-auth-chat-6c3844`.
Для отката восстановите из неё `previous-deploy.override.yml` в
`/home/ubuntu/kyrgyzgo-deploy.override.yml` и выполните из папки серверного проекта
`docker compose up -d --no-deps --no-build --wait backend`.
Дополнительный nullable-столбец email не мешает предыдущему образу; база автоматически не откатывается.
Базу, Redis, Caddy и существующие данные при обновлении не заменяли.
Commit и push в GitHub не выполнялись.

Ниже сохранена история предыдущего развёртывания и первоначальный план.

## Развёрнуто 23 октября 2026

Backend уже обновлён на `https://13.53.40.37`. Релиз: `20261023-4d704d65`.
Исходники работающего приложения: `/home/ubuntu/releases/20261023-4d704d65`.
Образ: `kyrgyzgo-api:release-20261023-4d704d65`.
Код передан архивом из текущей локальной рабочей копии; commit и push в GitHub не выполнялись.

Серверные Compose, Caddy, PostgreSQL и Redis сохранены. Перезапущен только backend.
В серверный `.env` добавлен `COMPOSE_FILE`, подключающий
`/home/ubuntu/kyrgyzgo-deploy.override.yml`: обычный `docker compose` из папки проекта
теперь использует новый релиз. Исходная серверная рабочая копия не перезаписывалась.

Резервная копия базы, конфигурации и старых исходников:
`/home/ubuntu/kyrgyzgo-backups/20261023-4d704d65`.
Образ для отката: `kyrgyzgo-api:rollback-20261023-4d704d65`.
Для отката укажите этот образ в серверном deployment override и выполните
`docker compose up -d --no-deps --no-build --wait backend` из `/home/ubuntu/Kyrgyz_Go`.
Не применяйте `--build` при откате: он пересоберёт образ из новых исходников.

Из-за малого диска использован проверенный прежний runtime с установленными зависимостями,
а не повторная установка всего `requirements.txt`. Сборка описана в серверном `Dockerfile.runtime`.
Работоспособность нового приложения и админки с этими зависимостями проверена отдельно.
После запуска через публичный HTTPS проверены регистрация, общий токен для чата и деталей,
закрытые детали для гостя и отзыв токена после выхода. Реальный Gemini собрал тестовые данные,
показал предварительную заявку без записи в админку; после фразы «Я готова бронировать тур»
заявка сохранилась и попала в выборку раздела «Заявки из чата». Тестовые записи удалены.
Диск сервера почти заполнен; перед дальнейшими сборками рекомендуется увеличить его размер.

Ниже — прежний план обновления через GitHub и результаты проверки до развёртывания,
а не описание текущего состояния сервера.

## Что проверено

Сервер `13.53.40.37`, SSH-пользователь `ubuntu`, проект `/home/ubuntu/Kyrgyz_Go`.
Compose-проект называется `kyrgyz_go`. В нём работают `backend`, `https`, `postgres`, `redis`.
На момент проверки backend и PostgreSQL healthy, HTTPS отвечает, миграция базы — `20261021_0003`.
Новый `/auth/register` ещё не развёрнут. Сервер содержит незакоммиченные изменения.

Локальный Compose отличается: сервис приложения называется `api`, PostgreSQL считается внешним.
Не заменяйте действующий серверный Compose или Caddyfile локальными копиями. Не выполняйте
`git reset --hard`, `git clean` или `docker compose down -v` для этого обновления.

Ниже код берётся из отдельного checkout, а серверные Compose, Caddyfile, переменные,
PostgreSQL, Redis и TLS-тома остаются прежними. Команды обновления в ходе проверки не выполнялись.

## 1. Отправить код на GitHub с компьютера

В PowerShell из папки проекта:

```powershell
git status
git add -A
git diff --cached --stat
git commit -m "Unify customer login and protect catalogue details"
git push origin main
```

Перед commit проверьте список подготовленных файлов. `.env` и ключей в нём быть не должно.
Новые `client_auth.py`, `catalogue_schema.py` и тесты обязательно должны попасть в commit.

## 2. Подключиться к серверу

```powershell
ssh -i "$env:USERPROFILE\.ssh\kyrgyzgo_ec2_deploy" ubuntu@13.53.40.37
```

Дальнейшие команды выполняются в Linux-терминале сервера.

## 3. Сохранить конфигурацию, базу и старый образ

```bash
set -e
umask 077
cd /home/ubuntu/Kyrgyz_Go
release_stamp=$(date -u +%Y%m%d-%H%M%S)
backup_dir="/home/ubuntu/kyrgyzgo-backups/$release_stamp"
release_dir="/home/ubuntu/releases/kyrgyzgo-$release_stamp"
mkdir -p "$backup_dir" /home/ubuntu/releases
cp docker-compose.yml Caddyfile .env "$backup_dir/"
git diff --binary > "$backup_dir/server-working-tree.patch"
sudo docker exec kyrgyzgo_postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$backup_dir/database.dump"
test -s "$backup_dir/database.dump"
old_image=$(sudo docker inspect --format '{{.Image}}' kyrgyzgo_backend)
rollback_image="kyrgyzgo-api:rollback-$release_stamp"
sudo docker image tag "$old_image" "$rollback_image"
printf '%s\n' "$rollback_image" > "$backup_dir/rollback-image.txt"
```

Если какая-либо команда завершилась ошибкой, остановитесь и устраните её до обновления.
`pg_dump` создаёт согласованную резервную копию без остановки работающего приложения.
Патч хранит изменения отслеживаемых файлов; отдельный checkout не изменяет исходные
неотслеживаемые серверные файлы, поэтому они остаются на месте.

## 4. Получить новую версию отдельно от серверных изменений

```bash
git fetch origin main
git worktree add --detach "$release_dir" origin/main
git -C "$release_dir" log -1 --oneline
test -f "$release_dir/mysite/api/client_auth.py"
test -f "$release_dir/mysite/database/catalogue_schema.py"
```

Если `git fetch` не имеет доступа к GitHub, сначала настройте доступ к репозиторию.
Не заменяйте этот шаг очисткой или перезаписью текущей серверной папки.

## 5. Собрать приложение с сохранением серверной конфигурации

```bash
deploy_override=/home/ubuntu/kyrgyzgo-deploy.override.yml
if test -f "$deploy_override"; then
    cp "$deploy_override" "$backup_dir/previous-deploy.override.yml"
fi
cat > "$deploy_override" <<EOF
services:
  backend:
    image: kyrgyzgo-api:release-$release_stamp
    build:
      context: $release_dir
      dockerfile: Dockerfile
EOF
sudo docker compose -p kyrgyz_go -f docker-compose.yml -f "$deploy_override" config --quiet
sudo docker compose -p kyrgyz_go -f docker-compose.yml -f "$deploy_override" build backend
sudo docker compose -p kyrgyz_go -f docker-compose.yml -f "$deploy_override" up -d --no-deps --wait --wait-timeout 180 backend
sudo docker compose -p kyrgyz_go -f docker-compose.yml -f "$deploy_override" ps
```

Перезапускается только приложение. При запуске его Dockerfile выполняет `alembic upgrade head`.
Для текущего обновления авторизации новых миграций нет. Уже существующая версия базы совпадает
с последней локальной миграцией. Краткий перерыв работы API при пересоздании контейнера возможен.

## 6. Проверить результат

```bash
curl --fail https://13.53.40.37/
python3 - <<'PY'
import json
import urllib.request
with urllib.request.urlopen('https://13.53.40.37/openapi.json', timeout=20) as response:
    paths = json.load(response)['paths']
assert '/auth/register' in paths
assert '/auth/login' in paths
print('Shared authentication is deployed')
PY
```

Затем проверьте через frontend или `/docs`:

1. Зарегистрируйте тестового клиента через `/auth/register`.
2. Один выданный токен должен открывать детали и `POST /chat/session`.
3. Без токена списки должны отвечать HTTP 200, детали — HTTP 401.
4. Соберите заявку в чате, проверьте сводку, напишите «Я готова бронировать тур».
5. В `/admin/` откройте «Заявки из чата» и проверьте контакты и параметры поездки.

Backend возвращает HTTP 401 для открытия общей формы регистрации во frontend.
Саму форму и повторное использование токена клиентское приложение подключает по
`docs/shared-client-auth.md`.

## Откат приложения при ошибке

В той же SSH-сессии, где сохранены переменные предыдущих шагов:

```bash
cat > "$deploy_override" <<EOF
services:
  backend:
    image: $rollback_image
EOF
sudo docker compose -p kyrgyz_go -f docker-compose.yml -f "$deploy_override" up -d --no-deps --no-build --wait --wait-timeout 180 backend
```

Это возвращает старый образ приложения, сохраняя базу. Для этого обновления схема базы не меняется.
При обновлениях с новыми миграциями возможность отката схемы нужно оценивать отдельно.

Для следующих обновлений используйте оба Compose-файла, включая
`/home/ubuntu/kyrgyzgo-deploy.override.yml`, и создавайте новый checkout с новой датой.
