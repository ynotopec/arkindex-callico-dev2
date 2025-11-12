from django.apps import AppConfig


class AnnotationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "callico.annotations"

    def ready(self):
        from callico.annotations import signals  # noqa
