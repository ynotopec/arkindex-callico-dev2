import json
import random
import uuid

import pytest
from django.urls import reverse
from pytest_lazy_fixtures import lf as lazy_fixture

from callico.annotations.models import TaskState
from callico.process.arkindex.exports import ARKINDEX_PUBLISH_METHODS
from callico.process.models import Process, ProcessMode
from callico.projects.models import CampaignMode

pytestmark = pytest.mark.django_db


def test_arkindex_export_process_create_anonymous(anonymous, campaign):
    "An anonymous user is redirected to the login page"
    export_url = reverse("arkindex-export-create", kwargs={"pk": campaign.id})
    response = anonymous.post(export_url)
    assert response.status_code == 302
    assert response.url == reverse("login") + f"?next={export_url}"


@pytest.mark.parametrize(
    "forbidden_campaign",
    [
        # Hidden campaign
        lazy_fixture("hidden_campaign"),
        # Public campaign
        lazy_fixture("public_campaign"),
        # Contributor rights on campaign project
        lazy_fixture("campaign"),
        # Moderator rights on campaign project
        lazy_fixture("moderated_campaign"),
    ],
)
def test_arkindex_export_process_create_forbidden(user, forbidden_campaign):
    response = user.post(reverse("arkindex-export-create", kwargs={"pk": forbidden_campaign.id}))
    assert response.status_code == 403


def test_arkindex_export_process_create_archived_campaign(admin, archived_campaign):
    response = admin.post(reverse("arkindex-export-create", kwargs={"pk": archived_campaign.id}))
    assert response.status_code == 403
    assert (
        str(response.context["error_message"])
        == "You cannot export annotations to Arkindex from a campaign marked as Archived"
    )


def test_arkindex_export_process_create_wrong_campaign_id(admin):
    response = admin.post(reverse("arkindex-export-create", kwargs={"pk": "cafecafe-cafe-cafe-cafe-cafecafecafe"}))
    assert response.status_code == 404
    assert response.context["exception"] == "No campaign matching this ID exists"


def test_arkindex_export_process_create_missing_or_wrong_provider(admin, managed_campaign, iiif_provider):
    managed_campaign.project.provider = iiif_provider
    managed_campaign.project.save()
    response = admin.post(reverse("arkindex-export-create", kwargs={"pk": managed_campaign.id}))
    assert response.status_code == 404
    assert (
        response.context["exception"]
        == "You can't create an Arkindex export process on a project that isn't linked to an Arkindex provider"
    )

    managed_campaign.project.provider = None
    managed_campaign.project.provider_object_id = None
    managed_campaign.project.save()
    response = admin.post(reverse("arkindex-export-create", kwargs={"pk": managed_campaign.id}))
    assert response.status_code == 404
    assert (
        response.context["exception"]
        == "You can't create an Arkindex export process on a project that isn't linked to an Arkindex provider"
    )


@pytest.mark.parametrize(
    "extra_information",
    [
        {"the predatory wasp": "of the pallisades"},
        {"worker_run_publication": None},
        {"worker_run_publication": ""},
    ],
)
def test_arkindex_export_process_create_missing_worker_run_publication(
    admin, managed_campaign, arkindex_provider, extra_information
):
    arkindex_provider.extra_information = extra_information
    arkindex_provider.save()
    response = admin.post(reverse("arkindex-export-create", kwargs={"pk": managed_campaign.id}))
    assert response.status_code == 404
    assert (
        response.context["exception"]
        == "You can't create an Arkindex export process on a project for which the Arkindex provider doesn't have a worker run ID for publication in its extra information field"
    )


@pytest.mark.parametrize("mode", [mode for mode in CampaignMode if mode not in ARKINDEX_PUBLISH_METHODS])
def test_arkindex_export_process_create_unsupported_campaign_mode(admin, managed_campaign, mode):
    managed_campaign.mode = mode
    managed_campaign.save()
    response = admin.post(reverse("arkindex-export-create", kwargs={"pk": uuid.uuid4()}))
    assert response.status_code == 404
    assert (
        response.context["exception"]
        == f"You cannot export results to Arkindex for a campaign of type {managed_campaign.get_mode_display()}"
    )


def test_arkindex_export_process_create_form_errors(admin, managed_campaign):
    response = admin.post(
        reverse("arkindex-export-create", kwargs={"pk": managed_campaign.id}),
        {"name": "", "exported_states": "unknown state"},
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 2
    assert form.errors == {
        "name": ["This field is required."],
        "exported_states": ["Select a valid choice. unknown state is not one of the available choices."],
    }
    assert Process.objects.count() == 0


@pytest.mark.parametrize(
    "custom_field, form_errors",
    [
        ({}, {"entities_order": ["This field is required."]}),
        (
            {"entities_order": [["invalid type", "instr"]], "concatenation_parent_type": "invalid type"},
            {
                "entities_order": [
                    "Select a valid choice. ['invalid type', 'instr'] is not one of the available choices."
                ],
                "concatenation_parent_type": [
                    "Select a valid choice. invalid type is not one of the available choices."
                ],
            },
        ),
    ],
)
def test_arkindex_export_process_create_form_errors_entity_form(custom_field, form_errors, admin, managed_campaign):
    managed_campaign.mode = CampaignMode.EntityForm
    managed_campaign.configuration = {"fields": [{"entity_type": "first_name", "instruction": "The first name"}]}
    managed_campaign.save()

    response = admin.post(
        reverse("arkindex-export-create", kwargs={"pk": managed_campaign.id}),
        {
            "name": "Arkindex export process",
            "exported_states": [TaskState.Annotated, TaskState.Validated],
            **custom_field,
        },
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == len(form_errors)
    assert form.errors == {
        **form_errors,
    }
    assert Process.objects.count() == 0


@pytest.mark.parametrize("mode", ARKINDEX_PUBLISH_METHODS)
@pytest.mark.parametrize(
    "exported_states",
    [[random.choice([TaskState.Annotated, TaskState.Validated])], [TaskState.Annotated, TaskState.Validated]],
)
@pytest.mark.parametrize("force_republication", [True, False, None])
@pytest.mark.parametrize("use_raw_publication", [True, False, None])
def test_arkindex_export_process_create(
    mocker,
    django_assert_num_queries,
    user,
    managed_campaign,
    mode,
    exported_states,
    force_republication,
    use_raw_publication,
):
    celery_mock = mocker.patch("callico.process.arkindex.tasks.arkindex_export.apply_async")
    managed_campaign.mode = mode
    if mode == CampaignMode.EntityForm:
        managed_campaign.configuration = {
            "fields": [
                {"entity_type": "first_name", "instruction": "The first name"},
                {"entity_type": "last_name", "instruction": "The last name"},
            ]
        }
    managed_campaign.save()

    # Prepare request data
    data = {"name": "Arkindex export process", "exported_states": exported_states}

    extra_config_field = {}
    if mode == CampaignMode.EntityForm:
        entities_order = [["last_name", "The last name"], ["first_name", "The first name"]]
        data["entities_order"] = list(map(json.dumps, entities_order))
        extra_config_field["entities_order"] = entities_order

        page_type = managed_campaign.project.types.get(name="Page")
        data["concatenation_parent_type"] = str(page_type.id)
        extra_config_field["concatenation_parent_type"] = data["concatenation_parent_type"]

    # These parameters are not required
    if force_republication is not None:
        data["force_republication"] = force_republication
    if use_raw_publication is not None:
        data["use_raw_publication"] = use_raw_publication

    with django_assert_num_queries(5 + (mode == CampaignMode.EntityForm)):
        response = user.post(reverse("arkindex-export-create", kwargs={"pk": managed_campaign.id}), data)

    assert response.status_code == 302

    process = Process.objects.get()
    assert process.name == "Arkindex export process"
    assert process.mode == ProcessMode.ArkindexExport.value
    assert process.configuration == {
        "arkindex_provider": str(managed_campaign.project.provider.id),
        "campaign": str(managed_campaign.id),
        "corpus": str(managed_campaign.project.provider_object_id),
        "worker_run": str(managed_campaign.project.provider.extra_information["worker_run_publication"]),
        "exported_states": exported_states,
        "force_republication": bool(force_republication),
        "use_raw_publication": bool(use_raw_publication) and mode != CampaignMode.Classification,
        **extra_config_field,
    }
    assert process.project == managed_campaign.project
    assert process.creator == user.user

    assert celery_mock.call_count == 1

    assert response.url == reverse("process-details", kwargs={"pk": process.id})
