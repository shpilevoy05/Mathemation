#!/bin/sh
# Резервная копия: дамп базы и работы учеников.
#
# Управляемая база провайдера уже делает свои снапшоты, но они живут в том же
# аккаунте и по тем же правам: ошибочное удаление кластера или потеря доступа
# уносит и их. Поэтому здесь — независимая копия, которую можно унести наружу.
#
# Запуск по расписанию (cron на сервере, ежедневно в 3:20):
#   20 3 * * * /srv/matemacia/infra/production/backup.sh >> /var/log/matemacia-backup.log 2>&1
set -eu

: "${BACKUP_DIR:=/srv/backups/matemacia}"
: "${BACKUP_KEEP_DAYS:=30}"
: "${PRIVATE_MEDIA_DIR:=/var/lib/docker/volumes/production_private-media/_data}"
: "${ENV_FILE:=/srv/matemacia/.env.production}"

# Пароль базы берётся из прод-окружения и не попадает ни в аргументы команды,
# ни в историю shell: пароль в командной строке виден всем в `ps`.
. "$ENV_FILE"
export PGPASSWORD="$POSTGRES_PASSWORD"
export PGSSLMODE="${POSTGRES_SSLMODE:-require}"
[ -n "${POSTGRES_SSLROOTCERT:-}" ] && export PGSSLROOTCERT="$POSTGRES_SSLROOTCERT"

stamp=$(date +%Y%m%d-%H%M%S)
target="$BACKUP_DIR/$stamp"
mkdir -p "$target"

echo "[$(date -Is)] дамп базы $POSTGRES_DB"
# Формат custom: восстанавливается выборочно и параллельно, в отличие от
# простого SQL-файла.
pg_dump \
    --host "$POSTGRES_HOST" --port "${POSTGRES_PORT:-5432}" \
    --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    --format=custom --compress=9 \
    --file "$target/db.dump"

echo "[$(date -Is)] работы учеников"
tar --create --gzip --file "$target/private-media.tar.gz" \
    --directory "$PRIVATE_MEDIA_DIR" .

# Проверка сразу после снятия: непроверенная копия — это надежда, а не бэкап.
echo "[$(date -Is)] проверка дампа"
pg_restore --list "$target/db.dump" > "$target/db.toc"
test -s "$target/db.toc"

( cd "$target" && sha256sum db.dump private-media.tar.gz > checksums.sha256 )

echo "[$(date -Is)] удаление копий старше $BACKUP_KEEP_DAYS дней"
find "$BACKUP_DIR" -maxdepth 1 -type d -name '20*' -mtime "+$BACKUP_KEEP_DAYS" \
    -exec rm -rf {} +

echo "[$(date -Is)] готово: $target"
du -sh "$target"
