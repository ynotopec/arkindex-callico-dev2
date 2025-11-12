import os
from pathlib import Path

import environ
from bleach.sanitizer import ALLOWED_ATTRIBUTES, ALLOWED_TAGS
from django.conf import settings
from django.core.exceptions import DisallowedHost
from django.utils.translation import gettext_lazy as _

BASE_DIR = Path(__file__).resolve(strict=True).parent.parent

env = environ.Env(
    DEBUG=(bool, True),
    ENVIRONMENT=(str, "dev"),
    SECRET_KEY=(str, "%paj+(x_^3rw*ge0@b"),
    ALLOWED_HOSTS=(list, ["127.0.0.1", "localhost"]),
    CORS_ALLOWED_ORIGINS=(list, ["http://localhost:8080", "http://127.0.0.1:8080"]),
    FRONTEND_DIR=(str, BASE_DIR / ".." / "front" / "dist"),
    DATABASE_URL=(str, "postgres://callico:callicopwd@localhost:5432/callico"),
    EMAIL_URL=(str, "consolemail://"),
    DEFAULT_FROM_EMAIL=(str, None),
    PROMETHEUS_METRICS_PORT=(int, 3000),
    SENTRY_DSN=(str, None),
    SENTRY_FRONTEND_DSN=(str, None),
    CSRF_TRUSTED_ORIGINS=(list, ["http://localhost:8000"]),
    REDIS_URL=(str, "redis://localhost:6379/0"),
    INSTANCE_URL=(str, "http://localhost:8000"),
    DATA_UPLOAD_MAX_NUMBER_FIELDS=(int, 1000),
    SIGNUP_ENABLED=(bool, False),
    PROJECT_CREATION_ALLOWED=(bool, False),
    STORAGE_ENDPOINT_URL=(str, None),
    STORAGE_BUCKET_NAME=(str, None),
    STORAGE_SSL_CA_PATH=(str, True),
    STORAGE_LOCATION=(str, ""),
)
environ.Env.read_env()

# Read Version either from Docker static file or local file
_version = "/etc/callico.version" if os.path.exists("/etc/callico.version") else BASE_DIR / "VERSION"
with open(_version) as f:
    VERSION = f.read().strip()

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env("DEBUG")

ENVIRONMENT = env("ENVIRONMENT")

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env("SECRET_KEY")

ALLOWED_HOSTS = env("ALLOWED_HOSTS")
CORS_ALLOWED_ORIGINS = env("CORS_ALLOWED_ORIGINS")

# Setup CSRF trusted origins explicitly as it's needed from Django 4
CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "django.forms",
    "django_prometheus",
    "corsheaders",
    "markdownify.apps.MarkdownifyConfig",
    "bulma",
    "rest_framework",
    "notifications",
    "callico.users",
    "callico.projects",
    "callico.annotations",
    "callico.process",
]

MIDDLEWARE = [
    "django_prometheus.middleware.PrometheusBeforeMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "callico.middleware.LanguageMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_prometheus.middleware.PrometheusAfterMiddleware",
]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}

ROOT_URLCONF = "callico.base.urls"

LOGIN_URL = "/users/login/"
LOGIN_REDIRECT_URL = "projects"
LOGOUT_REDIRECT_URL = "projects"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "base/templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "callico.base.context_processors.get_version",
                "callico.base.context_processors.get_signup_enabled",
                "callico.base.context_processors.get_project_creation_allowed",
                "callico.base.context_processors.get_frontend_sentry",
            ],
            "libraries": {
                "basefilters": "callico.base.basefilters",
            },
        },
    },
]

FORM_RENDERER = "django.forms.renderers.TemplatesSetting"

WSGI_APPLICATION = "callico.base.wsgi.application"

# Database
# https://docs.djangoproject.com/en/3.1/ref/settings/#databases
DATABASES = {"default": env.db()}


# Password validation
# https://docs.djangoproject.com/en/3.1/ref/settings/#auth-password-validators
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

AUTH_USER_MODEL = "users.User"


# Internationalization
# https://docs.djangoproject.com/en/3.1/topics/i18n/
LOCALE_PATHS = [BASE_DIR / "locale"]

LANGUAGE_CODE = "fr-fr"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True

LANGUAGES = [
    ("en", _("English")),
    ("fr", _("French")),
]

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/3.1/howto/static-files/
FRONTEND_DIR = env("FRONTEND_DIR")

STATIC_URL = "/static/"

STATIC_ROOT = BASE_DIR / "staticfiles"

STATICFILES_DIRS = [BASE_DIR / "base/static", FRONTEND_DIR, BASE_DIR / "projects/management/commands/fixtures"]

# Media files
MEDIA_URL = "/media/"

MEDIA_ROOT = BASE_DIR / "media"

# Default primary key field type
# https://docs.djangoproject.com/en/3.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Allowed number of parameters in GET/POST requests
DATA_UPLOAD_MAX_NUMBER_FIELDS = env("DATA_UPLOAD_MAX_NUMBER_FIELDS")

# Setup Email if defined in env variables
vars().update(env.email("EMAIL_URL"))
DEFAULT_FROM_EMAIL = SERVER_EMAIL = env("DEFAULT_FROM_EMAIL")

# Prometheus settings
PROMETHEUS_METRICS_PORT = env("PROMETHEUS_METRICS_PORT")
PROMETHEUS_EXPORT_MIGRATIONS = False

# Convert Markdown to HTML
MARKDOWNIFY = {
    "default": {
        "WHITELIST_TAGS": list(ALLOWED_TAGS)
        + [
            # Basic tags
            "p",
            # Titles
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            # Table
            "table",
            "thead",
            "tbody",
            "tfoot",
            "tr",
            "th",
            "td",
            # Image
            "img",
            # Codeblock
            "pre",
            # Definition list
            "dl",
            "dt",
            "dd",
        ],
        "WHITELIST_ATTRS": {**ALLOWED_ATTRIBUTES, "img": ["alt", "src"]},
        "MARKDOWN_EXTENSIONS": [
            "markdown.extensions.abbr",
            "markdown.extensions.def_list",
            "markdown.extensions.fenced_code",
            "markdown.extensions.nl2br",
            "markdown.extensions.tables",
        ],
    }
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "%(asctime)s [%(levelname)s] %(message)s"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
    },
    "loggers": {
        "callico": {
            "handlers": ["console"],
            "level": "INFO",
        },
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
        },
    },
}

# Support django-extensions
try:
    import django_extensions  # noqa

    INSTALLED_APPS.append("django_extensions")
except ImportError:
    pass

# Support django-debug-toolbar
try:
    import debug_toolbar.settings  # noqa

    MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")
    INSTALLED_APPS.append("debug_toolbar")
    INTERNAL_IPS = ["127.0.0.1"]
except ImportError:
    pass

# Import local settings if they exists
try:
    from .local_settings import *  # noqa
except ImportError:
    pass

# Support Sentry
SENTRY_DSN = env("SENTRY_DSN")
SENTRY_FRONTEND_DSN = env("SENTRY_FRONTEND_DSN")
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.logging import ignore_logger

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        release=VERSION,
        debug=DEBUG,
        environment=ENVIRONMENT,
        send_default_pii=True,
        integrations=[DjangoIntegration()],
        # Ignore "Invalid HTTP_HOST header" errors: https://gitlab.teklia.com/callico/callico/-/issues/382
        ignore_errors=[DisallowedHost],
    )
    # Ignore "Invalid HTTP_HOST header" logs: https://gitlab.teklia.com/callico/callico/-/issues/382
    ignore_logger("django.security.DisallowedHost")

# Celery
CELERY_BROKER_URL = CELERY_RESULT_BACKEND = env("REDIS_URL")

INSTANCE_URL = env("INSTANCE_URL")

SIGNUP_ENABLED = env("SIGNUP_ENABLED")

PROJECT_CREATION_ALLOWED = env("PROJECT_CREATION_ALLOWED")

# django-resized (for thumbnails)
DJANGORESIZED_DEFAULT_QUALITY = 75

# Setup django-storages for production use
if env("STORAGE_ENDPOINT_URL") is not None:
    # Always use S3 protocol, with modern signature and mark files as publicly readable
    settings.STORAGES["default"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
    }
    AWS_DEFAULT_ACL = "public-read"
    AWS_S3_SIGNATURE_VERSION = "s3v4"

    # Configure access to minio/ceph
    AWS_S3_ENDPOINT_URL = env("STORAGE_ENDPOINT_URL")
    AWS_STORAGE_BUCKET_NAME = env("STORAGE_BUCKET_NAME")

    # Use a provided CA to check minio SSL cert
    AWS_S3_VERIFY = env("STORAGE_SSL_CA_PATH")

    # Path prefix to prepend all uploads
    AWS_LOCATION = env("STORAGE_LOCATION")

    # If a file with the same name already exists, create a new one instead of replacing it
    AWS_S3_FILE_OVERWRITE = False

# https://docs.djangoproject.com/en/5.0/ref/settings/#std-setting-FORMS_URLFIELD_ASSUME_HTTPS
FORMS_URLFIELD_ASSUME_HTTPS = True
