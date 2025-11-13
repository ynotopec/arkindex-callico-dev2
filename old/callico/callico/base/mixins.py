from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.views.generic import TemplateView
from django_prometheus.exports import ExportToDjangoView


class PrometheusMetricsMixin(TemplateView):
    def get(self, *args, **kwargs):
        if int(self.request.get_port()) != settings.PROMETHEUS_METRICS_PORT:
            raise PermissionDenied
        return ExportToDjangoView(self.request)
