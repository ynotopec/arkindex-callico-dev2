import logging

import pytest
from django.urls import reverse
from pytest_lazy_fixtures import lf as lazy_fixture

from callico.process.models import PROCESS_FINAL_STATES, ProcessState

pytestmark = pytest.mark.django_db


def test_process_details_anonymous(anonymous, process):
    "An anonymous user is redirected to the login page"
    details_url = reverse("process-details", kwargs={"pk": process.id})
    response = anonymous.get(details_url)
    assert response.status_code == 302
    assert response.url == reverse("login") + f"?next={details_url}"


@pytest.mark.parametrize(
    "forbidden_process",
    [
        # Hidden process
        lazy_fixture("hidden_process"),
        # Public process
        lazy_fixture("public_process"),
        # Contributor rights on process project
        lazy_fixture("contributed_process"),
        # Moderator rights on process project
        lazy_fixture("moderated_process"),
    ],
)
def test_process_details_forbidden(user, forbidden_process):
    response = user.get(reverse("process-details", kwargs={"pk": forbidden_process.id}))
    assert response.status_code == 403


def test_process_details_wrong_process_id(user):
    response = user.get(reverse("process-details", kwargs={"pk": "cafecafe-cafe-cafe-cafe-cafecafecafe"}))
    assert response.status_code == 404
    assert response.context["exception"] == "No process matching this ID exists"


@pytest.mark.parametrize("state", ProcessState)
def test_process_details_get(user, process, state, django_assert_num_queries):
    process.state = state
    process.save()

    with django_assert_num_queries(4):
        response = user.get(reverse("process-details", kwargs={"pk": process.id}))
    assert response.status_code == 200

    assert response.context["process"] == process


@pytest.mark.parametrize("state", ProcessState)
def test_process_details_post(mocker, user, process, state, django_assert_num_queries):
    celery_mock = mocker.patch("callico.base.celery.app.control.revoke")

    process.state = state
    process.save()

    expected_queries = 4 if state in PROCESS_FINAL_STATES else 6
    with django_assert_num_queries(expected_queries):
        response = user.post(reverse("process-details", kwargs={"pk": process.id}))
    assert response.status_code == 302
    assert response.url == reverse("process-details", kwargs={"pk": process.id})

    process.refresh_from_db()
    # It isn't possible to stop processes which have already ended from the frontend but even if it was, it wouldn't have any side effect
    if state in PROCESS_FINAL_STATES:
        assert process.state == state
        assert not process.parsed_logs
    else:
        assert process.state == ProcessState.Error
        assert celery_mock.call_count == 1
        assert [
            (logging.ERROR, f"The process {process.id} was stopped by the user {user.user}"),
        ] == [(log["level"], log["content"]) for log in process.parsed_logs]
