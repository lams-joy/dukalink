"""DukaLink settings. All environment-specific values come from environment variables."""

import os
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def env(name: str, default: str | None = None) -> str | None:
    return os.environ.get(name, default)


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


DEBUG = env_bool("DJANGO_DEBUG", False)

SECRET_KEY = env("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "insecure-dev-only-key"  # never used when DEBUG is off
    else:
        raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is off.")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1" if DEBUG else "")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "apps.common",
    "apps.accounts",
    "apps.shops",
    "apps.catalog",
    "apps.inventory",
    "apps.sync",
    "apps.suppliers",
    "apps.orders",
    "apps.audit",
]

MIDDLEWARE = [
    "apps.common.middleware.RequestIDMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

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
            ]
        },
    }
]

# --- Database -------------------------------------------------------------
# PostgreSQL is the target. DB_ENGINE=sqlite is for quick local test runs only:
# it does not exercise row locking, so concurrency tests are skipped there.
if env("DB_ENGINE", "postgres") == "sqlite":
    DATABASES = {
        "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("POSTGRES_DB", "dukalink"),
            "USER": env("POSTGRES_USER", "dukalink"),
            "PASSWORD": env("POSTGRES_PASSWORD", "dukalink"),
            "HOST": env("POSTGRES_HOST", "localhost"),
            "PORT": env("POSTGRES_PORT", "5432"),
            "CONN_MAX_AGE": 60,
        }
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en"
TIME_ZONE = "UTC"  # store UTC; shops carry their own display timezone
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# --- API conventions (Phase 0) ---------------------------------------------
# * Errors:      {"error": {"code", "message", "details", "request_id"}}
# * Pagination:  {"count", "next", "previous", "results"}, page_size 50
# * Timestamps:  ISO 8601, UTC
# * Decimals:    serialised as strings, never floats
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.StandardPagination",
    "EXCEPTION_HANDLER": "apps.common.exceptions.api_exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "COERCE_DECIMAL_TO_STRING": True,
    "DEFAULT_THROTTLE_RATES": {"auth": env("AUTH_THROTTLE_RATE", "10/min")},
}

SPECTACULAR_SETTINGS = {
    "TITLE": "DukaLink API",
    "DESCRIPTION": "Inventory, wholesale ordering and group buying for duka owners.",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

# Provisional: the auth mechanism is still an open decision (decisions.md).
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
    "ROTATE_REFRESH_TOKENS": True,
}

# --- DukaLink business settings ---------------------------------------------
DEFAULT_PHONE_COUNTRY_CODE = env("DEFAULT_PHONE_COUNTRY_CODE", "254")
DEFAULT_CURRENCY = env("DEFAULT_CURRENCY", "KES")
# Wholesalers must be verified by a platform admin before their offers go live.
SUPPLIER_VERIFICATION_REQUIRED = env_bool("SUPPLIER_VERIFICATION_REQUIRED", True)
# Provisional: negative-stock policy is an open decision (decisions.md).
# False = a sale/decrease that would take stock below zero is rejected with 409.
ALLOW_NEGATIVE_STOCK = env_bool("ALLOW_NEGATIVE_STOCK", False)
QUANTITY_PLACES = 6
MIN_QUANTITY = Decimal("0.000001")

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
}
