from pathlib import Path
import os
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-replace-in-production")
DEBUG = os.environ.get("DEBUG", "True") == "True"
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "slots",
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

ROOT_URLCONF = "core.urls"

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.debug",
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

STATIC_URL = "/static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ── B2B Slots System Config ─────────────────────────────────────────────────
GRAPHQL_URL = os.environ.get("GRAPHQL_URL", "https://gis-api.aiesec.org/graphql")
GQL_EMAIL   = os.environ.get("GQL_EMAIL", "")
GQL_PASSWORD= os.environ.get("GQL_PASSWORD", "")
LC_ID       = os.environ.get("LC_ID", None)

OOS_SHEET_ID   = os.environ.get("OOS_SHEET_ID", "1U_Z2MXcZ_vDUKNGbPDNOhnl6nwcPiRdaUZlY3xhbfqw")
OOS_SHEET_GID  = os.environ.get("OOS_SHEET_GID", "2082291020")
OOS_SHEET_NAME = os.environ.get("OOS_SHEET_NAME", "Sheet1")
APPS_SCRIPT_PUSH_URL = os.environ.get("APPS_SCRIPT_PUSH_URL", "")

LOGGING = {
    "version": 1,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
