#!/bin/sh
set -eu

python manage.py collectstatic --noinput
# Para una sola instancia. En Render se puede mover a un pre-deploy command.
if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    python manage.py migrate --noinput
fi

exec gunicorn barberia.wsgi:application \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers "${WEB_CONCURRENCY:-2}" \
    --access-logfile - \
    --error-logfile -
