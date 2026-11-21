#!/bin/sh
set -eu

python -m flask --app glori migrate
python -m flask --app glori bootstrap-admin
exec python -m gunicorn --bind "0.0.0.0:${PORT:-10000}" --workers 2 'glori:create_app()'
