#!/usr/bin/env bash
# Render build script — install deps, collect static files, run migrations.
set -o errexit

pip install --upgrade pip
pip install -r requirements.txt

python manage.py collectstatic --noinput
python manage.py migrate --noinput
python manage.py bootstrap_admin
