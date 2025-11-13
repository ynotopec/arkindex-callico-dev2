from urllib.parse import urljoin

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponseRedirect
from django.http.response import Http404
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import translation
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView, UpdateView, View

from callico.projects.forms import REQUIRED_CSS_CLASS
from callico.users.forms import SignUpForm
from callico.users.models import User
from callico.users.tasks import send_email
from callico.users.tokens import account_activation_token


class SignUpView(CreateView):
    form_class = SignUpForm
    template_name = "signup.html"

    def dispatch(self, request, *args, **kwargs):
        if not settings.SIGNUP_ENABLED:
            raise Http404(_("Sign up feature is deactivated on this instance"))

        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        user = form.save()

        with translation.override(user.preferred_language):
            message = render_to_string(
                "mails/email_confirmation.html",
                context={
                    "confirmation_url": urljoin(
                        settings.INSTANCE_URL,
                        reverse(
                            "confirm-email",
                            kwargs={
                                "uidb64": urlsafe_base64_encode(force_bytes(user.pk)),
                                "token": account_activation_token.make_token(user),
                            },
                        ),
                    ),
                },
            )

            # Send the confirmation mail to the user
            send_email.delay(
                _("Welcome to Callico - Your account awaits activation"),
                message,
                [user.email],
            )

        # Authenticate the created account
        login(self.request, user)

        messages.add_message(
            self.request,
            messages.SUCCESS,
            _("Your account has been created, you'll receive a mail to confirm your email address in the near future."),
        )

        return super().form_valid(form)

    def get_success_url(self):
        return self.request.GET.get("next") or reverse("home")


class LoginView(auth_views.LoginView):
    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.required_css_class = REQUIRED_CSS_CLASS
        return form


class ConfirmEmailView(View):
    def get(self, request, uidb64, token, *args, **kwargs):
        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            user = None

        if user is not None and account_activation_token.check_token(user, token):
            user.email_validated = True
            user.save()
            messages.add_message(request, messages.SUCCESS, _("Your account has been confirmed."))
        else:
            messages.add_message(
                request,
                messages.ERROR,
                _("The confirmation link was invalid, possibly because it has already been used."),
            )

        return HttpResponseRedirect(reverse("home"))


class PasswordResetView(auth_views.PasswordResetView):
    template_name = "reset_password.html"

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.required_css_class = REQUIRED_CSS_CLASS
        return form

    def form_valid(self, form):
        messages.add_message(
            self.request,
            messages.INFO,
            _("If your account exists, an email with password reset instructions has been sent."),
        )

        return super().form_valid(form)

    def get_success_url(self):
        return reverse("login")


class PasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    template_name = "reset_password_confirm.html"

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.required_css_class = REQUIRED_CSS_CLASS
        return form

    def form_valid(self, form):
        messages.add_message(self.request, messages.SUCCESS, _("Your password has been updated."))

        return super().form_valid(form)

    def get_success_url(self):
        return reverse("login")


class UserUpdate(LoginRequiredMixin, UpdateView):
    model = User
    fields = ["display_name", "preferred_language"]
    template_name = "user_update.html"

    def get_object(self):
        return self.request.user

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.required_css_class = REQUIRED_CSS_CLASS
        return form

    def form_valid(self, form):
        with translation.override(self.request.user.preferred_language):
            messages.add_message(self.request, messages.SUCCESS, gettext("Your profile has been saved."))

        return super().form_valid(form)

    def get_success_url(self):
        return reverse("user-update")
