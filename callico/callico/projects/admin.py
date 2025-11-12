from django import forms
from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from callico.annotations.admin import TaskInline
from callico.projects.models import (
    Authority,
    AuthorityValue,
    Campaign,
    Class,
    Element,
    Image,
    Membership,
    Project,
    Provider,
    Type,
)


class MembershipInline(admin.TabularInline):
    model = Membership
    raw_id_fields = ("project",)


class ProjectAdmin(admin.ModelAdmin):
    inlines = (MembershipInline,)

    list_display = ("id", "name", "public", "provider", "created")
    list_filter = ("public", "provider")
    fieldsets = (
        (None, {"fields": ("name", "description", "illustration", "public", "invite_token")}),
        (_("Provider relationship"), {"fields": ("provider", "provider_object_id", "provider_extra_information")}),
    )
    search_fields = ("name", "provider_object_id")
    ordering = ("-created", "name")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("provider")

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        obj.fetch_extra_info(request.user)


class ProviderAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "type", "api_url")
    fieldsets = (
        (None, {"fields": ("name", "type")}),
        (_("Provider API"), {"fields": ("api_url", "api_token", "extra_information")}),
    )
    search_fields = ("name",)
    ordering = ("name",)


class ElementForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance:
            return
        queryset = Element.objects.exclude(id=self.instance.id)
        if self.instance.project_id:
            queryset = queryset.filter(project_id=self.instance.project_id)
        self.fields["parent"].queryset = queryset


class ElementAdmin(admin.ModelAdmin):
    form = ElementForm
    inlines = (TaskInline,)

    list_display = ("id", "name", "type", "project", "provider", "provider_object_id")
    list_filter = ("project", "type", "provider")
    fieldsets = (
        (None, {"fields": ("name", "type")}),
        (_("Project"), {"fields": ("project", "parent", "order")}),
        (_("Display"), {"fields": ("image", "polygon")}),
        (
            _("Provider relationship"),
            {
                "fields": (
                    "provider",
                    "provider_object_id",
                    "transcription",
                    "metadata",
                    "entities",
                )
            },
        ),
    )
    search_fields = ("name", "provider_object_id")
    readonly_fields = ("order", "transcription", "metadata", "entities")


class ImageAdmin(admin.ModelAdmin):
    list_display = ("id", "iiif_url", "width", "height")
    search_fields = ("iiif_url",)


class ClassAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "project", "provider")
    list_filter = ("project", "provider")
    fieldsets = (
        (None, {"fields": ("name", "project")}),
        (_("Provider relationship"), {"fields": ("provider", "provider_object_id")}),
    )
    search_fields = ("name",)


class TypeAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "folder", "project", "provider")
    list_filter = ("project", "provider")
    fieldsets = (
        (None, {"fields": ("name", "folder", "color", "project")}),
        (_("Provider relationship"), {"fields": ("provider", "provider_object_id")}),
    )
    search_fields = ("name",)


class CampaignAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "project", "mode", "creator")
    list_filter = ("mode",)
    search_fields = ("name",)
    ordering = ("-created", "name")
    readonly_fields = ("csv_export", "xlsx_export")


class AuthorityAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "description")
    search_fields = ("name",)
    ordering = ("name",)


class AuthorityValueAdmin(admin.ModelAdmin):
    list_display = ("id", "authority", "value", "authority_value_id")
    list_filter = ("authority",)
    search_fields = ("value", "authority_value_id")
    ordering = ("authority", "authority_value_id", "value")


admin.site.register(Project, ProjectAdmin)
admin.site.register(Provider, ProviderAdmin)
admin.site.register(Element, ElementAdmin)
admin.site.register(Image, ImageAdmin)
admin.site.register(Class, ClassAdmin)
admin.site.register(Type, TypeAdmin)
admin.site.register(Campaign, CampaignAdmin)
admin.site.register(Authority, AuthorityAdmin)
admin.site.register(AuthorityValue, AuthorityValueAdmin)
