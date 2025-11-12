from django.middleware.locale import LocaleMiddleware
from django.utils import translation


class LanguageMiddleware(LocaleMiddleware):
    def process_request(self, request):
        super().process_request(request)

        if request.user.is_authenticated:
            language = request.user.preferred_language
            translation.activate(language)
            request.LANGUAGE_CODE = translation.get_language()
