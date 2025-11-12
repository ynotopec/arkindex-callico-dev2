from django.contrib.auth import views as auth_views
from django.urls import path

from callico.users.views import (
    ConfirmEmailView,
    LoginView,
    PasswordResetConfirmView,
    PasswordResetView,
    SignUpView,
    UserUpdate,
)

urlpatterns = [
    path("signup/", SignUpView.as_view(), name="signup"),
    path("confirm/<uidb64>/<token>/", ConfirmEmailView.as_view(), name="confirm-email"),
    path("login/", LoginView.as_view(template_name="login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("password-reset/", PasswordResetView.as_view(), name="password_reset"),
    path("<uidb64>/<token>/", PasswordResetConfirmView.as_view(), name="password_reset_confirm"),
    path("profile/", UserUpdate.as_view(), name="user-update"),
]
