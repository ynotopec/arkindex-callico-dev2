import pytest
from django.urls import reverse
from pytest_lazy_fixtures import lf as lazy_fixture

from callico.process.models import Process, ProcessMode
from callico.projects.models import XLSX_SUPPORTED_CAMPAIGN_MODES, CampaignMode

pytestmark = pytest.mark.django_db


def test_xlsx_export_process_create_anonymous(anonymous, campaign):
    "An anonymous user is redirected to the login page"
    create_url = reverse("xlsx-export-create", kwargs={"pk": campaign.id})
    response = anonymous.post(create_url)
    assert response.status_code == 302
    assert response.url == reverse("login") + f"?next={create_url}"


@pytest.mark.parametrize(
    "forbidden_campaign",
    [
        # Hidden campaign
        lazy_fixture("hidden_campaign"),
        # Public campaign
        lazy_fixture("public_campaign"),
        # Contributor rights on campaign project
        lazy_fixture("campaign"),
    ],
)
def test_xlsx_export_process_create_forbidden(user, forbidden_campaign):
    response = user.post(reverse("xlsx-export-create", kwargs={"pk": forbidden_campaign.id}))
    assert response.status_code == 403


def test_xlsx_export_process_create_archived_campaign(admin, archived_campaign):
    response = admin.post(reverse("xlsx-export-create", kwargs={"pk": archived_campaign.id}))
    assert response.status_code == 403
    assert (
        str(response.context["error_message"]) == "You cannot export results as XLSX from a campaign marked as Archived"
    )


def test_xlsx_export_process_create_wrong_campaign_id(admin):
    response = admin.post(reverse("xlsx-export-create", kwargs={"pk": "cafecafe-cafe-cafe-cafe-cafecafecafe"}))
    assert response.status_code == 404
    assert response.context["exception"] == "No campaign matching this ID exists"


@pytest.mark.parametrize("mode", [mode for mode in CampaignMode if mode not in XLSX_SUPPORTED_CAMPAIGN_MODES])
def test_xlsx_export_process_create_wrong_campaign_mode(mode, admin, managed_campaign):
    managed_campaign.mode = mode
    managed_campaign.save()
    response = admin.post(reverse("xlsx-export-create", kwargs={"pk": managed_campaign.id}))
    assert response.status_code == 404
    assert (
        response.context["exception"]
        == f"You cannot export results as XLSX for a campaign of type {managed_campaign.get_mode_display()}"
    )


@pytest.mark.parametrize("mode", XLSX_SUPPORTED_CAMPAIGN_MODES)
def test_xlsx_export_process_create(mocker, django_assert_num_queries, user, mode, managed_campaign):
    celery_mock = mocker.patch("callico.process.tasks.xlsx_export.apply_async")

    managed_campaign.mode = mode
    managed_campaign.save()
    with django_assert_num_queries(5):
        response = user.post(reverse("xlsx-export-create", kwargs={"pk": managed_campaign.id}))

    assert response.status_code == 302

    process = Process.objects.get()
    assert process.name == f"XLSX export for {managed_campaign.name}"
    assert process.mode == ProcessMode.XLSXExport.value
    assert process.configuration == {"campaign_id": str(managed_campaign.id)}
    assert process.project == managed_campaign.project
    assert process.creator == user.user

    assert celery_mock.call_count == 1

    assert response.url == reverse("process-details", kwargs={"pk": process.id})
