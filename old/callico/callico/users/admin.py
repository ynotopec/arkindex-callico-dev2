from urllib.parse import urljoin

from django import forms
from django.conf import settings
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import ReadOnlyPasswordHashField
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import translation
from django.utils.translation import gettext_lazy as _

from callico.projects.admin import MembershipInline
from callico.users.models import Comment, User
from callico.users.tasks import send_email

# Setup titles for administration panel
admin.site.site_title = "Callico"
admin.site.site_header = "Callico"
admin.site.index_title = _("Callico Administration panel")


class UserChangeForm(forms.ModelForm):
    """A form for updating users. Includes all the fields on
    the user, but replaces the password field with admin's
    password hash display field.
    """

    password = ReadOnlyPasswordHashField()

    class Meta:
        model = User
        fields = ("email", "password", "is_admin", "is_staff")

    def clean_password(self):
        # Regardless of what the user provides, return the initial value.
        # This is done here, rather than on the field, because the
        # field does not have access to the initial value
        return self.initial["password"]


class UserAdmin(BaseUserAdmin):
    # The form used to change user instances
    form = UserChangeForm
    inlines = (MembershipInline,)

    list_display = ("email", "display_name", "is_admin", "is_staff", "created")
    list_filter = ("is_admin", "is_staff")
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "email",
                    "password",
                )
            },
        ),
        (_("Permissions"), {"fields": ("email_validated", "is_admin", "is_staff")}),
        (
            _("Preferences"),
            {
                "fields": (
                    "display_name",
                    "preferred_language",
                )
            },
        ),
    )
    # add_fieldsets is not a standard ModelAdmin attribute.
    # UserAdmin overrides get_fieldsets to use this attribute when creating a user.
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "password1",
                    "password2",
                    "is_admin",
                    "is_staff",
                    "display_name",
                    "preferred_language",
                ),
            },
        ),
    )
    search_fields = (
        "display_name",
        "email",
    )
    ordering = ("email",)
    filter_horizontal = ()

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:
            with translation.override(obj.preferred_language):
                message = render_to_string(
                    "mails/new_account.html",
                    context={
                        "reset_password_url": urljoin(settings.INSTANCE_URL, reverse("password_reset")),
                        "instance_url": settings.INSTANCE_URL,
                    },
                )
                # Send an email after the creation of a new account
                send_email.delay(
                    _("Welcome to Callico - Your account awaits activation"),
                    message,
                    [obj.email],
                )


class CommentAdmin(admin.ModelAdmin):
    list_display = ("id", "task", "user", "created")


admin.site.register(User, UserAdmin)
admin.site.register(Comment, CommentAdmin)
