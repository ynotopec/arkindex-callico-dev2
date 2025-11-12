from django.contrib import admin

from callico.process.models import Process


class ProcessAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "state", "creator", "mode", "project")
    list_filter = ("mode", "state", "project", "creator")
    search_fields = ("name",)
    ordering = ("-created", "name")


admin.site.register(Process, ProcessAdmin)
