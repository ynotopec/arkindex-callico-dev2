from django import forms
from django.contrib import admin
from django.urls import resolve
from django.utils.translation import gettext_lazy as _

from callico.annotations.models import Annotation, Task, TaskUser
from callico.projects.models import CAMPAIGN_CLOSED_STATES, Campaign
from callico.users.models import User


class TaskInline(admin.TabularInline):
    model = Task

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        resolved = resolve(request.path_info)
        element_id = resolved.kwargs.get("object_id")
        if element_id:
            element = self.parent_model.objects.get(id=element_id)
            kwargs["queryset"] = Campaign.objects.filter(project=element.project).exclude(
                state__in=CAMPAIGN_CLOSED_STATES
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class TaskUserInline(admin.TabularInline):
    model = TaskUser

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        resolved = resolve(request.path_info)
        task_id = resolved.kwargs.get("object_id")
        if task_id:
            task = self.parent_model.objects.get(id=task_id)
            kwargs["queryset"] = User.objects.filter(memberships__project=task.element.project)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class TaskAdmin(admin.ModelAdmin):
    inlines = (TaskUserInline,)

    list_display = ("id", "campaign", "element_id")
    list_filter = ("campaign",)
    ordering = ("-created",)


class TaskUserAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "state", "task_id")
    list_filter = ("state", "user", "task__campaign")
    ordering = ("-created",)


class AnnotationForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance:
            return
        queryset = Annotation.objects.exclude(id=self.instance.id)
        if self.instance.user_task_id:
            queryset = queryset.filter(user_task_id=self.instance.user_task_id)
        self.fields["parent"].queryset = queryset


class AnnotationAdmin(admin.ModelAdmin):
    form = AnnotationForm

    list_display = ("id", "campaign", "created")
    list_filter = ("user_task__task__campaign",)
    ordering = ("-created",)
    readonly_fields = ("version",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.prefetch_related("user_task__task__campaign")

    @admin.display(description=_("Campaign"))
    def campaign(self, obj):
        return obj.user_task.task.campaign


admin.site.register(Task, TaskAdmin)
admin.site.register(TaskUser, TaskUserAdmin)
admin.site.register(Annotation, AnnotationAdmin)
