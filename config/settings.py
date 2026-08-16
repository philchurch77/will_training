"""
Django settings for Will's training app.

Two people use this and it runs on one small machine, so it stays simple:
SQLite, no external services, no third-party runtime dependencies beyond a
static-file server.

Locally nothing needs configuring - the defaults are development defaults. In
production every knob comes from an environment variable, and the app refuses
to start insecurely (see the guard at the bottom).
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env_flag(name, default=False):
    return os.environ.get(name, "1" if default else "0").lower() in {"1", "true", "yes"}


def env_list(name):
    return [item.strip() for item in os.environ.get(name, "").split(",") if item.strip()]


# --- Security -------------------------------------------------------------
DEBUG = env_flag("WILL_DEBUG", default=True)

# In production this MUST come from the environment. The insecure fallback is
# only ever used when DEBUG is on; the guard at the end of this file enforces it.
SECRET_KEY = os.environ.get("WILL_SECRET_KEY", "dev-only-insecure-key")

# Render sets RENDER_EXTERNAL_HOSTNAME automatically.
ALLOWED_HOSTS = env_list("WILL_HOSTS")
if render_host := os.environ.get("RENDER_EXTERNAL_HOSTNAME"):
    ALLOWED_HOSTS.append(render_host)
if DEBUG and not ALLOWED_HOSTS:
    # Local dev, including reaching the dev server from a phone on the LAN.
    ALLOWED_HOSTS = ["*"]

CSRF_TRUSTED_ORIGINS = env_list("WILL_TRUSTED_ORIGINS")
if render_host:
    CSRF_TRUSTED_ORIGINS.append(f"https://{render_host}")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "training",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

if not DEBUG:
    # In production WhiteNoise serves the CSS, JS and icon, so no separate web
    # server is needed. With DEBUG on, Django's own staticfiles app does it.
    MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# WILL_DB_PATH points at a persistent disk in production. Without it the
# database lives next to the code, which is right for local development and
# WRONG on a host with an ephemeral filesystem - see the README.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get("WILL_DB_PATH") or BASE_DIR / "db.sqlite3",
        "OPTIONS": {"timeout": 20},
    }
}

# PINs are four digits by design (see README). Django's validators are aimed at
# passwords and would reject every possible PIN, so they are switched off. The
# login view throttles by IP instead.
AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Europe/London"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    # Compressed but NOT manifest-hashed. The hashing variant makes every page
    # 500 if collectstatic has not been run, which is a nasty trap in an app
    # meant to be handed over. Cache busting is handled by bumping the service
    # worker's CACHE name instead.
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# The login throttle lives in the cache. Local memory is deliberate: the app
# runs as a single worker (see render.yaml), so one process holds all the
# state and no Redis is needed for two users.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "will-training",
    }
}

# --- Auth -----------------------------------------------------------------
LOGIN_URL = "training:login"
LOGIN_REDIRECT_URL = "training:today"
LOGOUT_REDIRECT_URL = "training:login"

# Will enters his code once and stays signed in for a year. Every request
# pushes the expiry back, so in practice he never sees the pad again.
SESSION_COOKIE_AGE = 60 * 60 * 24 * 365
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

# --- PIN throttling -------------------------------------------------------
# A 4-digit code is 10,000 guesses. On a home network that hardly matters; on
# the public internet it does, so wrong guesses are throttled per IP and then
# capped globally. See the README before loosening any of this.
PIN_MAX_ATTEMPTS = 5           # wrong guesses before the first lockout
PIN_LOCKOUT_SECONDS = 60       # first lockout, doubling each time
PIN_MAX_LOCKOUT_SECONDS = 3600
PIN_GLOBAL_MAX_ATTEMPTS = 100  # wrong guesses from anywhere, per hour
PIN_GLOBAL_WINDOW_SECONDS = 3600

# --- Production hardening -------------------------------------------------
if not DEBUG:
    # Render terminates TLS at its proxy and forwards this header.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_flag("WILL_SSL_REDIRECT", default=True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"
    X_FRAME_OPTIONS = "DENY"
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True

    # Fail loudly rather than quietly serving the internet with a known key.
    if SECRET_KEY == "dev-only-insecure-key":
        raise RuntimeError(
            "WILL_SECRET_KEY must be set when DEBUG is off. "
            "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(50))\""
        )
    if not ALLOWED_HOSTS:
        raise RuntimeError(
            "WILL_HOSTS must list the domain this is served from when DEBUG is off."
        )
