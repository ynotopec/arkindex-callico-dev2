from django.conf import settings


def get_version(request):
    return {"VERSION": settings.VERSION}


def get_signup_enabled(request):
    return {"SIGNUP_ENABLED": settings.SIGNUP_ENABLED}


def get_project_creation_allowed(request):
    return {"PROJECT_CREATION_ALLOWED": settings.PROJECT_CREATION_ALLOWED}


def get_frontend_sentry(request):
    """
    Get the public frontend Sentry DSN to use in the Javascript build.
    Also return the current instance environment.
    """
    return {"SENTRY_DSN": settings.SENTRY_FRONTEND_DSN, "ENVIRONMENT": settings.ENVIRONMENT}
