#!/bin/sh
# Восстановление из копии. Отдельный скрипт, потому что восстановление нужно
# репетировать: бэкап, который ни разу не разворачивали, не считается рабочим.
#
#   ./restore.sh /srv/backups/matemacia/20260809-032000 [цель]
#
# Второй аргумент — имя базы, куда разворачивать. По умолчанию это
# `${POSTGRES_DB}_restore`, а не боевая база: учебная тревога не должна
# заканчиваться потерей продакшена. Чтобы восстановить поверх боевой, имя
# указывается явно и подтверждается вводом.
set -eu

backup_dir="${1:?укажите каталог копии}"
: "${ENV_FILE:=/srv/matemacia/.env.production}"
. "$ENV_FILE"

target_db="${2:-${POSTGRES_DB}_restore}"
export PGPASSWORD="$POSTGRES_PASSWORD"
export PGSSLMODE="${POSTGRES_SSLMODE:-require}"
[ -n "${POSTGRES_SSLROOTCERT:-}" ] && export PGSSLROOTCERT="$POSTGRES_SSLROOTCERT"

echo "[$(date -Is)] проверка контрольных сумм"
( cd "$backup_dir" && sha256sum --check checksums.sha256 )

if [ "$target_db" = "$POSTGRES_DB" ]; then
    printf 'Восстановление ПОВЕРХ боевой базы %s. Введите её имя для подтверждения: ' "$POSTGRES_DB"
    read -r confirm
    [ "$confirm" = "$POSTGRES_DB" ] || { echo "Отменено."; exit 1; }
fi

psql_admin() {
    psql --host "$POSTGRES_HOST" --port "${POSTGRES_PORT:-5432}" \
        --username "$POSTGRES_USER" --dbname postgres --no-psqlrc \
        --set ON_ERROR_STOP=on "$@"
}

echo "[$(date -Is)] создание базы $target_db"
psql_admin --command "DROP DATABASE IF EXISTS \"$target_db\";"
psql_admin --command "CREATE DATABASE \"$target_db\" OWNER \"$POSTGRES_USER\";"

echo "[$(date -Is)] разворачивание дампа"
pg_restore \
    --host "$POSTGRES_HOST" --port "${POSTGRES_PORT:-5432}" \
    --username "$POSTGRES_USER" --dbname "$target_db" \
    --no-owner --jobs 4 \
    "$backup_dir/db.dump"

echo "[$(date -Is)] работы учеников"
restore_media="${RESTORE_MEDIA_DIR:-/srv/restore/private-media}"
mkdir -p "$restore_media"
tar --extract --gzip --file "$backup_dir/private-media.tar.gz" --directory "$restore_media"

cat <<EOF

[$(date -Is)] готово.
База:   $target_db
Файлы:  $restore_media

Проверить перед тем, как считать учение успешным:
  1. Число учеников и попыток совпадает с ожидаемым:
     psql -d $target_db -c "select count(*) from accounts_studentprofile;"
     psql -d $target_db -c "select count(*), max(created_at) from practice_attempt;"
  2. Последний платёж на месте:
     psql -d $target_db -c "select max(paid_at) from billing_payment where status='succeeded';"
  3. Файлы читаются: ls -R "$restore_media" | head
EOF
