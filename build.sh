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

# migrate and seed_drills deliberately do NOT run here. The persistent disk
# at /var/data is only mounted at runtime, so during the build there is no
# database to open and sqlite fails with "unable to open database file".
# They run from startCommand in render.yaml instead.
