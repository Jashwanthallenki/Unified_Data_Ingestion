import os
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BASE_DIR.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-secret-not-for-production")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = [h.strip() for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",") if h.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "tenants",
    "lookups",
    "ingestion",
    "activities",
    "mock_travel",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "breathe_esg.urls"

# Built React lives at frontend/dist after `npm run build`.
FRONTEND_BUILD_DIR = REPO_ROOT / "frontend" / "dist"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # Frontend dist first so the built React index.html wins over the placeholder
        # when present; placeholder used otherwise.
        "DIRS": [FRONTEND_BUILD_DIR, BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "breathe_esg.wsgi.application"
ASGI_APPLICATION = "breathe_esg.asgi.application"

# Database: prefer DATABASE_URL (Postgres locally via docker-compose; Postgres add-on in prod).
# SQLite fallback exists only to make `manage.py check` work before Postgres is up.
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
if DATABASE_URL:
    DATABASES = {"default": dj_database_url.parse(DATABASE_URL, conn_max_age=600)}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS: list = []
# Vite builds React assets to frontend/dist/assets and emits URLs prefixed with /static/.
# Mounting the assets dir under the "assets/" prefix keeps the served paths matching what
# the built index.html references (/static/assets/index-XXXX.js etc.).
if (FRONTEND_BUILD_DIR / "assets").exists():
    STATICFILES_DIRS.append(("assets", FRONTEND_BUILD_DIR / "assets"))
# Use uncompressed-but-hashed storage so a missing-asset reference doesn't blow up the
# manifest. Vite already produces hashed filenames, so we don't need ManifestStaticFiles.
STATICFILES_STORAGE = "whitenoise.storage.CompressedStaticFilesStorage"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
}

# Prototype: single-tenant, no auth. Open CORS.
CORS_ALLOW_ALL_ORIGINS = True

# Groq config
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_TIMEOUT_S = float(os.environ.get("GROQ_TIMEOUT_S", "20"))

# Default tenant identity (used by seed_tenant and request scoping)
DEFAULT_TENANT_SLUG = os.environ.get("DEFAULT_TENANT_SLUG", "demo-enterprise-client")
DEFAULT_TENANT_NAME = os.environ.get("DEFAULT_TENANT_NAME", "Demo Enterprise Client")

# Larger uploads — sample SAP files can be >2.5 MB default.
DATA_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {"class": "logging.StreamHandler"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "breathe_esg": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}
