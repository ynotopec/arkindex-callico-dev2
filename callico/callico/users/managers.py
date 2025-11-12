from django.contrib.auth.models import BaseUserManager
from django.utils.translation import gettext_lazy as _


class UserManager(BaseUserManager):
    def create_user(self, display_name, email, password=None, is_admin=False, is_staff=False):
        """
        Create and save a user with the given display name, email and password.
        """
        if not display_name:
            raise ValueError(_("Users must have a display name"))

        if not email:
            raise ValueError(_("Users must have an email address"))

        user = self.model(
            display_name=display_name,
            email=self.normalize_email(email),
            is_admin=is_admin,
            is_staff=is_staff,
        )

        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, display_name, email, password):
        """
        Create and save a superuser with the given display name, email and password.
        """
        return self.create_user(display_name, email, password, is_admin=True, is_staff=True)
