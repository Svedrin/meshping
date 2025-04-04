from pathlib import Path
import os


BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "django-insecure-2svcr!j9%^_(^)$%)vvt1j&0$w)&_l&oxacnb1mkurd4f--xmg"
DEBUG = True
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    #    'django.contrib.admin',
    #    'django.contrib.auth',
    #    'django.contrib.contenttypes',
    #    'django.contrib.sessions',
    #    'django.contrib.messages',
    "django.contrib.staticfiles",
    "meshping",
]

# MIDDLEWARE = [
#    'django.middleware.security.SecurityMiddleware',
#    'django.contrib.sessions.middleware.SessionMiddleware',
#    'django.middleware.common.CommonMiddleware',
#    'django.middleware.csrf.CsrfViewMiddleware',
#    'django.contrib.auth.middleware.AuthenticationMiddleware',
#    'django.contrib.messages.middleware.MessageMiddleware',
#    'django.middleware.clickjacking.XFrameOptionsMiddleware',
# ]

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
    #    {
    #        'BACKEND': 'django.template.backends.django.DjangoTemplates',
    #        'DIRS': [],
    #        'APP_DIRS': True,
    #        'OPTIONS': {
    #            'context_processors': [
    #                'django.template.context_processors.debug',
    #                'django.template.context_processors.request',
    ##                'django.contrib.auth.context_processors.auth',
    ##                'django.contrib.messages.context_processors.messages',
    #            ],
    #        },
    #    },
]
# WSGI_APPLICATION = 'meshping.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.1/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db" / "db.sqlite3",
    }
}

# AUTH_PASSWORD_VALIDATORS = [
#    {
#        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
#    },
#    {
#        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
#    },
#    {
#        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
#    },
#    {
#        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
#    },
# ]

# LANGUAGE_CODE = 'en-us'
# TIME_ZONE = 'UTC'
# USE_I18N = True
# USE_TZ = True

STATIC_URL = "ui/"
STATICFILES_DIRS = [
    BASE_DIR / "ui",
]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
