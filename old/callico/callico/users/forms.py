from django import forms
from django.conf import settings
from django.contrib.auth.forms import BaseUserCreationForm
from django.utils import translation

from callico.projects.forms import REQUIRED_CSS_CLASS
from callico.users.models import User


class SignUpForm(BaseUserCreationForm):
    required_css_class = REQUIRED_CSS_CLASS

    preferred_language = forms.ChoiceField(
        widget=forms.HiddenInput(),
        required=True,
        choices=settings.LANGUAGES,
    )

    class Meta:
        model = User
        fields = ("display_name", "email", "password1", "password2", "preferred_language")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Setting the initial value here instead of above for it to be reinterpreted each time the form is loaded
        self.fields["preferred_language"].initial = translation.get_language()
