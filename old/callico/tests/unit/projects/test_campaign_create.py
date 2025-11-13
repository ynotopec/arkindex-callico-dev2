import pytest
from django.urls import reverse
from pytest_lazy_fixtures import lf as lazy_fixture

from callico.projects.models import Campaign, CampaignMode, CampaignState

pytestmark = pytest.mark.django_db


def test_campaign_create_anonymous(anonymous, project):
    "An anonymous user is redirected to the login page"
    create_url = reverse("campaign-create", kwargs={"project_id": project.id})
    response = anonymous.post(create_url)
    assert response.status_code == 302
    assert response.url == reverse("login") + f"?next={create_url}"


@pytest.mark.parametrize(
    "forbidden_project",
    [
        # Hidden project
        lazy_fixture("hidden_project"),
        # Public project
        lazy_fixture("public_project"),
        # Contributor rights on project
        lazy_fixture("project"),
        # Moderator rights on project
        lazy_fixture("moderated_project"),
    ],
)
def test_campaign_create_forbidden(user, forbidden_project):
    response = user.post(reverse("campaign-create", kwargs={"project_id": forbidden_project.id}))
    assert response.status_code == 403


def test_campaign_create_wrong_project_id(user):
    response = user.post(reverse("campaign-create", kwargs={"project_id": "cafecafe-cafe-cafe-cafe-cafecafecafe"}))
    assert response.status_code == 404
    assert response.context["exception"] == "No project matching this ID exists"


def test_campaign_create_missing_required_fields(user, managed_project):
    response = user.post(
        reverse("campaign-create", kwargs={"project_id": managed_project.id}), {"name": "", "mode": ""}
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 2
    assert form.errors == {"name": ["This field is required."], "mode": ["This field is required."]}
    assert Campaign.objects.count() == 0


def test_campaign_create_invalid_mode(user, managed_project):
    response = user.post(
        reverse("campaign-create", kwargs={"project_id": managed_project.id}),
        {"name": "A campaign", "mode": "unknown mode"},
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 1
    assert form.errors == {"mode": ["Select a valid choice. unknown mode is not one of the available choices."]}
    assert Campaign.objects.count() == 0


def test_campaign_create_no_classes(user, managed_project):
    response = user.post(
        reverse("campaign-create", kwargs={"project_id": managed_project.id}),
        {"name": "A campaign", "mode": CampaignMode.Classification},
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 1
    assert form.errors == {"mode": ["There are no classes available for this project"]}
    assert Campaign.objects.count() == 0


def test_campaign_create_no_non_folder_types(user, managed_project):
    response = user.post(
        reverse("campaign-create", kwargs={"project_id": managed_project.id}),
        {"name": "A campaign", "mode": CampaignMode.Elements},
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 1
    assert form.errors == {"mode": ["There are no non-folder element types available for this project"]}
    assert Campaign.objects.count() == 0


def test_campaign_create_no_types(user, managed_project):
    response = user.post(
        reverse("campaign-create", kwargs={"project_id": managed_project.id}),
        {"name": "A campaign", "mode": CampaignMode.ElementGroup},
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 1
    assert form.errors == {"mode": ["There are no element types available for this project"]}
    assert Campaign.objects.count() == 0


def test_campaign_create_get(user, managed_project, django_assert_num_queries):
    with django_assert_num_queries(4):
        response = user.get(
            reverse("campaign-create", kwargs={"project_id": managed_project.id}),
        )
    assert response.status_code == 200

    assert response.context["project"] == managed_project


@pytest.mark.parametrize("mode", CampaignMode)
def test_campaign_create_post(user, mode, managed_project, django_assert_num_queries):
    managed_project.classes.create(name="Cat")
    managed_project.types.create(name="Paragraph")

    expected_query = 6 if mode in [CampaignMode.Classification, CampaignMode.Elements, CampaignMode.ElementGroup] else 5
    with django_assert_num_queries(expected_query):
        response = user.post(
            reverse("campaign-create", kwargs={"project_id": managed_project.id}),
            {
                "name": "A campaign",
                "mode": mode,
                "description": "This is an annotation campaign",
            },
        )
    assert response.status_code == 302
    assert Campaign.objects.count() == 1

    created = Campaign.objects.first()
    assert created.name == "A campaign"
    assert created.mode == mode
    assert created.description == "This is an annotation campaign"
    assert created.project == managed_project
    assert created.creator == user.user
    assert created.state == CampaignState.Created.value

    assert response.url == reverse("campaign-update", kwargs={"pk": created.id})
