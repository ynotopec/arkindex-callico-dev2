from django.apps import AppConfig


class ProjectsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "callico.projects"

    def ready(self):
        from callico.projects import signals  # noqa
