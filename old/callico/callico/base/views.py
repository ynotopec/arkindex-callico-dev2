from django.shortcuts import render
from django.views.i18n import set_language


def bad_request_view(request, exception):
    return render(request, "400.html", status=400, context={"error_message": exception})


def forbidden_view(request, exception):
    return render(request, "403.html", status=403, context={"error_message": exception})


def custom_set_language(request):
    response = set_language(request)

    language_cookie = response.cookies.get("django_language")
    if request.method == "POST" and request.user.is_authenticated and language_cookie:
        request.user.preferred_language = language_cookie.value
        request.user.save()

    return response
