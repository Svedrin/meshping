from pathlib import Path
import os


BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "django-insecure-2svcr!j9%^_(^)$%)vvt1j&0$w)&_l&oxacnb1mkurd4f--xmg"
DEBUG = True
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "meshping",
]

ROOT_URLCONF = "meshping.urls"

# TODO the APP_DIRS seem to not work as I imagined for the jinja2 backend
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.jinja2.Jinja2",
        "DIRS": [
            os.path.join(BASE_DIR, "meshping/templates"),
        ],
        "APP_DIRS": False,
        "OPTIONS": {
            "environment": "meshping.jinja2.environment",
        },
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db" / "db.sqlite3",
    }
}

STATIC_URL = "ui/"
STATICFILES_DIRS = [
    BASE_DIR / "ui",
]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
