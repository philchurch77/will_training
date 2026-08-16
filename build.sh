#!/usr/bin/env bash
# Render build step. Anything that must happen before the app starts serving
# goes here - Render runs it on every deploy.
set -o errexit

pip install --upgrade pip

# requirements.txt is generated from uv.lock - regenerate it with:
#   uv export --no-dev --no-hashes --no-emit-project -o requirements.txt
pip install -r requirements.txt

# Collect CSS, JS and the icons so WhiteNoise can serve them.
python manage.py collectstatic --no-input

# Safe to run every deploy: applies only new migrations.
python manage.py migrate

# Creates the drills, plan, badges and Will's profile on the very first
# deploy. On later deploys it updates them in place and leaves his logged
# sessions and his changed code alone.
python manage.py seed_drills
