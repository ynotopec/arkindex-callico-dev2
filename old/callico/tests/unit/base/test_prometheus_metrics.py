import re

import pytest
from django.conf import settings
from django.urls import reverse

pytestmark = pytest.mark.django_db


def test_prometheus_metrics_invalid_port(user):
    "Prometheuse metrics are only available on the specified port"
    response = user.get(reverse("metrics"))
    assert response.status_code == 403


def test_prometheus_metrics(user):
    response = user.get(reverse("metrics"), SERVER_PORT=settings.PROMETHEUS_METRICS_PORT)
    assert response.status_code == 200
    data = response.getvalue().decode("utf-8")
    results = dict(re.findall(r"^(\S+)\s(\S*)$", data, re.MULTILINE))
    assert (
        float(
            results[
                'django_http_requests_total_by_view_transport_method_total{method="GET",transport="http",view="metrics"}'
            ]
        )
        > 1
    )
