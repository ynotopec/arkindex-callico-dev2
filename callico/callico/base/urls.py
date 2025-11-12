from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from django.views.generic.base import RedirectView

from callico.base.mixins import PrometheusMetricsMixin
from callico.base.views import custom_set_language

handler400 = "callico.base.views.bad_request_view"
handler403 = "callico.base.views.forbidden_view"

urlpatterns = [
    path("lang/setlang/", custom_set_language, name="custom_set_language"),
    path("admin/", admin.site.urls),
    path("users/", include("callico.users.urls")),
    path("metrics", PrometheusMetricsMixin.as_view(), name="metrics"),
    path("projects/", include("callico.projects.urls")),
    path("annotation/", include("callico.annotations.urls")),
    path("processes/", include("callico.process.urls")),
    # Redirect home to projects list
    path("", RedirectView.as_view(url="/projects/"), name="home"),
    path("api/v1/", include("callico.base.api_v1")),
]

if "debug_toolbar" in settings.INSTALLED_APPS:
    import debug_toolbar

    urlpatterns += [
        path("__debug__/", include(debug_toolbar.urls)),
    ]


if settings.DEBUG:
    from django.conf.urls.static import static

    # Serve media files from development server
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
