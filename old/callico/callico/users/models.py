import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser
from django.db import models
from django.utils.translation import gettext_lazy as _

from callico.users.managers import UserManager


class User(AbstractBaseUser):
    email = models.EmailField(max_length=255, unique=True, verbose_name=_("Email"))
    is_admin = models.BooleanField(default=False, verbose_name=_("Is administrator"))
    is_staff = models.BooleanField(default=False, verbose_name=_("Is staff"))
    # This field is required for some functions even if we do not handle inactive users.
    # E.g. Password reset form which use a specific email comparison.
    # https://github.com/django/django/blob/65b880b7268dd8fe97fde5af77bede46305eb499/django/contrib/auth/forms.py#L280
    is_active = models.BooleanField(default=True, verbose_name=_("Is active"))
    email_validated = models.BooleanField(default=False, verbose_name=_("Email validated"))

    # User preferences
    display_name = models.CharField(verbose_name=_("Display name"))
    preferred_language = models.CharField(
        default="en", choices=settings.LANGUAGES, verbose_name=_("Preferred language")
    )

    created = models.DateTimeField(auto_now_add=True, verbose_name=_("Created"))
    updated = models.DateTimeField(auto_now=True, verbose_name=_("Updated"))

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["display_name"]

    objects = UserManager()

    class Meta:
        verbose_name = _("User")
        verbose_name_plural = _("Users")

    def __str__(self):
        return self.display_name

    @property
    def is_superuser(self):
        return self.is_admin

    def has_perm(self, perm, obj=None):
        "Does the user have a specific permission?"
        # Simplest possible answer: Yes, always
        return True

    def has_module_perms(self, app_label):
        "Does the user have permissions to view the app `app_label`?"
        # Simplest possible answer: Yes, always
        return True


class Comment(models.Model):
    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    user = models.ForeignKey("users.User", on_delete=models.CASCADE, related_name="comments", verbose_name=_("User"))
    task = models.ForeignKey(
        "annotations.Task", on_delete=models.CASCADE, related_name="comments", verbose_name=_("Task")
    )
    content = models.TextField(blank=True, default="", verbose_name=_("Content"))

    created = models.DateTimeField(auto_now_add=True, verbose_name=_("Created"))
    updated = models.DateTimeField(auto_now=True, verbose_name=_("Updated"))

    class Meta:
        verbose_name = _("Comment")
        verbose_name_plural = _("Comments")
        indexes = [models.Index(fields=["user", "task"])]
