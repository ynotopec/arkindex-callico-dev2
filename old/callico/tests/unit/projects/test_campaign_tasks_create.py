import math

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from pytest_lazy_fixtures import lf as lazy_fixture

from callico.annotations.models import Task, TaskState, TaskUser
from callico.projects.forms import (
    ALGORITHM_CHOICES,
    ALGORITHM_RANDOM,
    ALGORITHM_SEQUENTIAL,
    ELEMENT_SELECTION_ALL,
    ELEMENT_SELECTION_CHOICES,
    ELEMENT_SELECTION_UNUSED,
)
from callico.projects.models import CAMPAIGN_CLOSED_STATES, Campaign, CampaignMode, CampaignState, Role

pytestmark = pytest.mark.django_db


def test_campaign_tasks_create_anonymous(anonymous, campaign):
    "An anonymous user is redirected to the login page"
    create_url = reverse("tasks-create", kwargs={"pk": campaign.id})
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
        # Moderator rights on campaign project
        lazy_fixture("moderated_campaign"),
    ],
)
def test_campaign_tasks_create_forbidden(user, forbidden_campaign):
    response = user.post(reverse("tasks-create", kwargs={"pk": forbidden_campaign.id}))
    assert response.status_code == 403


@pytest.mark.parametrize("state", CAMPAIGN_CLOSED_STATES)
def test_campaign_tasks_create_closed_campaign(user, state, managed_campaign):
    managed_campaign.state = state
    managed_campaign.save()
    response = user.post(reverse("tasks-create", kwargs={"pk": managed_campaign.id}))
    assert response.status_code == 403
    assert (
        str(response.context["error_message"])
        == f"You cannot create tasks for a campaign marked as {state.capitalize()}"
    )


def test_campaign_tasks_create_no_images(user, managed_campaign):
    managed_campaign.project.elements.filter(image__isnull=False).delete()
    response = user.post(reverse("tasks-create", kwargs={"pk": managed_campaign.id}))
    assert response.status_code == 404
    assert response.context["exception"] == "You cannot create tasks for a project that does not contain images"


def test_campaign_tasks_create_wrong_id(user):
    response = user.post(reverse("tasks-create", kwargs={"pk": "cafecafe-cafe-cafe-cafe-cafecafecafe"}))
    assert response.status_code == 404
    assert response.context["exception"] == "No campaign matching this ID exists"


@pytest.mark.parametrize(
    "params, error",
    [
        (
            {"users": []},
            {
                "users": [
                    "When you aren't creating unassigned tasks for volunteers or generating a preview task, this field is required."
                ]
            },
        ),
        (
            {"preview": "Preview a single task"},
            {
                "element_selection": [
                    "When you are creating assigned tasks for contributors or generating a preview task, this field is required."
                ]
            },
        ),
    ],
)
def test_campaign_tasks_create_missing_required_fields(user, params, error, managed_campaign):
    response = user.post(
        reverse("tasks-create", kwargs={"pk": managed_campaign.id}), {"type": "", "algorithm": "", **params}
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 3
    assert form.errors == {"type": ["This field is required."], "algorithm": ["This field is required."], **error}
    assert Task.objects.count() == 0
    assert TaskUser.objects.count() == 0
    assert managed_campaign.state == CampaignState.Created


def test_campaign_tasks_create_invalid_algorithm(user, contributor, managed_campaign):
    response = user.post(
        reverse("tasks-create", kwargs={"pk": managed_campaign.id}),
        {
            "type": managed_campaign.project.types.get(name="Page").id,
            "users": [contributor.user.id],
            "algorithm": "unknown algorithm",
            "element_selection": ELEMENT_SELECTION_ALL,
        },
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 1
    assert form.errors == {
        "algorithm": ["Select a valid choice. unknown algorithm is not one of the available choices."]
    }
    assert Task.objects.count() == 0
    assert TaskUser.objects.count() == 0
    assert managed_campaign.state == CampaignState.Created


def test_campaign_tasks_create_invalid_type(user, contributor, managed_campaign):
    response = user.post(
        reverse("tasks-create", kwargs={"pk": managed_campaign.id}),
        {
            "type": "unknown type",
            "users": [contributor.user.id],
            "algorithm": ALGORITHM_RANDOM,
            "element_selection": ELEMENT_SELECTION_ALL,
        },
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 1
    assert form.errors == {"type": ["Select a valid choice. unknown type is not one of the available choices."]}
    assert Task.objects.count() == 0
    assert TaskUser.objects.count() == 0
    assert managed_campaign.state == CampaignState.Created


def test_campaign_tasks_create_invalid_users(user, managed_campaign):
    response = user.post(
        reverse("tasks-create", kwargs={"pk": managed_campaign.id}),
        {
            "type": managed_campaign.project.types.get(name="Page").id,
            "users": [user.user.id],
            "algorithm": ALGORITHM_RANDOM,
            "element_selection": ELEMENT_SELECTION_ALL,
        },
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 1
    assert form.errors == {"users": [f"Select a valid choice. {user.user.id} is not one of the available choices."]}
    assert Task.objects.count() == 0
    assert TaskUser.objects.count() == 0
    assert managed_campaign.state == CampaignState.Created


@pytest.mark.parametrize(
    "value, expected_error",
    [
        (
            "unknown element selection",
            "Select a valid choice. unknown element selection is not one of the available choices.",
        ),
        (ELEMENT_SELECTION_UNUSED, "There is no unused Page elements on this campaign"),
    ],
)
def test_campaign_tasks_create_invalid_element_selection(user, value, expected_error, contributor, managed_campaign):
    if value == ELEMENT_SELECTION_UNUSED:
        # Use all existing elements on this campaign to raise an error
        TaskUser.objects.bulk_create(
            TaskUser(
                user=contributor.user,
                state=TaskState.Pending,
                task=Task.objects.create(element=element, campaign=managed_campaign),
            )
            for element in managed_campaign.project.elements.all()
        )
    # The count should remain the same after the POST
    # Each Task is assigned one time so Task.objects.count() == TaskUser.objects.count()
    before_count = Task.objects.count()

    response = user.post(
        reverse("tasks-create", kwargs={"pk": managed_campaign.id}),
        {
            "type": managed_campaign.project.types.get(name="Page").id,
            "users": [contributor.user.id],
            "algorithm": ALGORITHM_RANDOM,
            "element_selection": value,
        },
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 1
    assert form.errors == {"element_selection": [expected_error]}
    assert Task.objects.count() == before_count
    assert TaskUser.objects.count() == before_count
    assert managed_campaign.state == CampaignState.Created


def test_campaign_tasks_create_elements_already_used_in_another_campaign(user, contributor, managed_campaign):
    """
    If Project.elements are used in one campaign, they shouldn't be considered already in use
    for a completely different campaign
    """
    page_type = managed_campaign.project.types.get(name="Page").id
    new_campaign = Campaign.objects.create(
        project=managed_campaign.project,
        name="Another campaign",
        creator=user.user,
        mode=CampaignMode.Transcription,
        state=CampaignState.Created,
        configuration={"key": "value"},
    )
    # Create TaskUser objects for all Elements in the Project in the managed_campaign Campaign
    TaskUser.objects.bulk_create(
        TaskUser(
            user=contributor.user,
            state=TaskState.Pending,
            task=Task.objects.create(element=element, campaign=managed_campaign),
        )
        for element in managed_campaign.project.elements.all()
    )

    # All elements are already used in managed_campaign
    response = user.post(
        reverse("tasks-create", kwargs={"pk": managed_campaign.id}),
        {
            "type": page_type,
            "users": [contributor.user.id],
            "algorithm": ALGORITHM_RANDOM,
            "element_selection": ELEMENT_SELECTION_UNUSED,
        },
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 1
    assert form.errors == {"element_selection": ["There is no unused Page elements on this campaign"]}

    # But not in new_campaign
    response = user.post(
        reverse("tasks-create", kwargs={"pk": new_campaign.id}),
        {
            "type": page_type,
            "users": [contributor.user.id],
            "algorithm": ALGORITHM_RANDOM,
            "element_selection": ELEMENT_SELECTION_UNUSED,
        },
    )
    assert response.status_code == 302
    assert new_campaign.state == CampaignState.Created

    nb_elements = new_campaign.project.elements.filter(type_id=page_type).count()
    assert Task.objects.filter(campaign=new_campaign).count() == nb_elements
    assert TaskUser.objects.filter(task__campaign=new_campaign).count() == nb_elements


@pytest.mark.parametrize(
    "max_number, message",
    [
        ("-1", "Ensure this value is greater than or equal to 1."),
        ("not a number", "Enter a whole number."),
        (3.14, "Enter a whole number."),
    ],
)
def test_campaign_tasks_create_invalid_max_number(user, max_number, message, contributor, managed_campaign):
    response = user.post(
        reverse("tasks-create", kwargs={"pk": managed_campaign.id}),
        {
            "type": managed_campaign.project.types.get(name="Page").id,
            "users": [contributor.user.id],
            "algorithm": ALGORITHM_RANDOM,
            "element_selection": ELEMENT_SELECTION_ALL,
            "max_number": max_number,
        },
    )
    assert response.status_code == 200
    form = response.context["form"]
    assert len(form.errors) == 1
    assert form.errors == {"max_number": [message]}
    assert Task.objects.count() == 0
    assert TaskUser.objects.count() == 0
    assert managed_campaign.state == CampaignState.Created


@pytest.mark.parametrize("preview", [False, True])
@pytest.mark.parametrize("create_unassigned_tasks", [False, True])
def test_campaign_tasks_create_no_user_selected(
    user, new_contributor, preview, create_unassigned_tasks, django_assert_num_queries, managed_campaign
):
    managed_campaign.mode = CampaignMode.Classification
    managed_campaign.save()
    managed_campaign.project.memberships.create(user=new_contributor, role=Role.Contributor)
    elements = managed_campaign.project.elements.filter(image__isnull=False).order_by("parent_id", "order")

    body = {
        "type": managed_campaign.project.types.get(name="Page").id,
        "users": [],
        "algorithm": ALGORITHM_SEQUENTIAL,
        "element_selection": ELEMENT_SELECTION_ALL,
    }

    if create_unassigned_tasks:
        body["create_unassigned_tasks"] = True

    if preview:
        body["preview"] = "Preview a single task"

    num_queries = 16 if preview else (9 if create_unassigned_tasks else 8)
    with django_assert_num_queries(num_queries):
        response = user.post(reverse("tasks-create", kwargs={"pk": managed_campaign.id}), body)

    if not preview and not create_unassigned_tasks:
        assert response.status_code == 200
        form = response.context["form"]
        assert len(form.errors) == 1
        assert form.errors == {
            "users": [
                "When you aren't creating unassigned tasks for volunteers or generating a preview task, this field is required."
            ],
        }
        assert Task.objects.count() == 0
        assert TaskUser.objects.count() == 0
        assert managed_campaign.state == CampaignState.Created
    else:
        assert response.status_code == 302
        assert managed_campaign.state == CampaignState.Created

        assert Task.objects.count() == (1 if preview else elements.count())
        assert TaskUser.objects.count() == (1 if preview else 0)

        if preview:
            user_task = TaskUser.objects.get()
            assert user_task.user == user.user
            assert user_task.is_preview


@pytest.mark.parametrize("algorithm", [choice[0] for choice in ALGORITHM_CHOICES])
@pytest.mark.parametrize("element_selection", [choice[0] for choice in ELEMENT_SELECTION_CHOICES])
@pytest.mark.parametrize("max_number", ["", 5, 1000])
def test_campaign_tasks_create_assigned(
    user,
    new_contributor,
    algorithm,
    element_selection,
    max_number,
    contributor,
    managed_campaign,
    django_assert_num_queries,
):
    managed_campaign.project.memberships.create(user=new_contributor, role=Role.Contributor)
    elements = managed_campaign.project.elements.filter(image__isnull=False).order_by("parent_id", "order")
    first_element = elements.first()
    TaskUser.objects.create(user=user.user, task=Task.objects.create(element=first_element, campaign=managed_campaign))

    if element_selection == ELEMENT_SELECTION_UNUSED:
        # Removing the already used element from the expected queryset
        elements = elements.exclude(id=first_element.id)

    elements_to_use = elements
    if max_number:
        elements_to_use = elements[: max_number * 2]

    nb_elements = elements_to_use.count()
    nb_assigned_tasks = nb_elements + 1

    num_queries = 13 if element_selection == ELEMENT_SELECTION_ALL else 14
    with django_assert_num_queries(num_queries):
        with CaptureQueriesContext(connection):
            response = user.post(
                reverse("tasks-create", kwargs={"pk": managed_campaign.id}),
                {
                    "type": managed_campaign.project.types.get(name="Page").id,
                    "users": [new_contributor.id, contributor.user.id],
                    "algorithm": algorithm,
                    "element_selection": element_selection,
                    "max_number": max_number,
                    "create_unassigned_tasks": False,
                },
            )
            query_index = 9 if element_selection == ELEMENT_SELECTION_ALL else 10
            query_defining_elements_order = connection.queries[query_index]["sql"]

    managed_campaign.refresh_from_db()
    assert response.status_code == 302
    assert managed_campaign.state == CampaignState.Created
    # If the random algorithm is used alongside with the max_number attribute we can't really know
    # if the already used element was picked in the random queryset and skipped (= one less task)
    total_tasks = Task.objects.count()
    assert total_tasks == nb_elements or total_tasks == nb_elements + 1

    unassigned_tasks = Task.objects.filter(user_tasks__isnull=True)
    assert unassigned_tasks.count() == 0

    assert TaskUser.objects.count() == nb_assigned_tasks
    assert TaskUser.objects.filter(user=contributor.user).count() == math.ceil(nb_elements / 2)
    assert TaskUser.objects.filter(user=new_contributor).count() == math.floor(nb_elements / 2)
    # Assert all TaskUser are in draft
    assert TaskUser.objects.filter(state=TaskState.Draft).count() == nb_assigned_tasks

    contributor_elements = list(
        TaskUser.objects.filter(user=contributor.user).order_by("created").values_list("task__element_id")
    )
    new_contributor_elements = list(
        TaskUser.objects.filter(user=new_contributor).order_by("created").values_list("task__element_id")
    )
    sequential_contributor_elements = list(elements_to_use.values_list("id")[: math.ceil(nb_elements / 2)])
    sequential_user_elements = list(elements_to_use.values_list("id")[math.ceil(nb_elements / 2) :])
    if algorithm == ALGORITHM_SEQUENTIAL:
        assert contributor_elements == sequential_contributor_elements
        assert new_contributor_elements == sequential_user_elements
        assert (
            'ORDER BY "projects_element"."parent_id" ASC, "projects_element"."order" ASC'
            in query_defining_elements_order
        )
    # Using the random algorithm we can't really assert how tasks were
    # assigned but we can at least check that the proper ordering was used
    if algorithm == ALGORITHM_RANDOM:
        assert "ORDER BY RANDOM() ASC" in query_defining_elements_order

    assert response.url == reverse("admin-campaign-task-list", kwargs={"pk": managed_campaign.id}) + "?state=draft"


@pytest.mark.parametrize("algorithm", [choice[0] for choice in ALGORITHM_CHOICES])
def test_campaign_tasks_create_unassigned(
    user,
    new_contributor,
    algorithm,
    contributor,
    managed_campaign,
    django_assert_num_queries,
):
    managed_campaign.project.memberships.create(user=new_contributor, role=Role.Contributor)
    elements = managed_campaign.project.elements.filter(image__isnull=False).order_by("parent_id", "order")
    first_element = elements.first()
    TaskUser.objects.create(user=user.user, task=Task.objects.create(element=first_element, campaign=managed_campaign))

    nb_elements = elements.count()

    with django_assert_num_queries(10):
        with CaptureQueriesContext(connection):
            response = user.post(
                reverse("tasks-create", kwargs={"pk": managed_campaign.id}),
                {
                    "type": managed_campaign.project.types.get(name="Page").id,
                    "algorithm": algorithm,
                    "create_unassigned_tasks": True,
                },
            )
            query_defining_elements_order = connection.queries[8]["sql"]

    managed_campaign.refresh_from_db()
    assert response.status_code == 302
    assert managed_campaign.state == CampaignState.Created
    total_tasks = Task.objects.count()
    assert total_tasks == nb_elements

    unassigned_tasks = Task.objects.filter(user_tasks__isnull=True)
    assert unassigned_tasks.count() == nb_elements - 1

    assert TaskUser.objects.count() == 1

    new_tasks = list(unassigned_tasks.order_by("created").values_list("element_id"))
    sequential_elements = list(elements.exclude(id=first_element.id).values_list("id"))
    if algorithm == ALGORITHM_SEQUENTIAL:
        assert new_tasks == sequential_elements
        assert (
            'ORDER BY "projects_element"."parent_id" ASC, "projects_element"."order" ASC'
            in query_defining_elements_order
        )
    # Using the random algorithm we can't really assert how tasks were
    # assigned but we can at least check that the proper ordering was used
    if algorithm == ALGORITHM_RANDOM:
        assert sorted(new_tasks) == sorted(sequential_elements)
        assert "ORDER BY RANDOM() ASC" in query_defining_elements_order

    assert response.url == reverse("admin-campaign-task-list", kwargs={"pk": managed_campaign.id}) + "?user_id=no_user"


@pytest.mark.parametrize("algorithm", [choice[0] for choice in ALGORITHM_CHOICES])
@pytest.mark.parametrize("element_selection", [choice[0] for choice in ELEMENT_SELECTION_CHOICES])
@pytest.mark.parametrize("max_number", ["", 5, 1000])
def test_campaign_tasks_create_both(
    user,
    new_contributor,
    algorithm,
    element_selection,
    max_number,
    contributor,
    managed_campaign,
    django_assert_num_queries,
):
    managed_campaign.project.memberships.create(user=new_contributor, role=Role.Contributor)
    elements = managed_campaign.project.elements.filter(image__isnull=False).order_by("parent_id", "order")
    first_element = elements.first()
    TaskUser.objects.create(user=user.user, task=Task.objects.create(element=first_element, campaign=managed_campaign))

    if element_selection == ELEMENT_SELECTION_UNUSED:
        # Removing the already used element from the expected queryset
        elements = elements.exclude(id=first_element.id)

    elements_to_use = elements
    nb_elements_not_to_use = 0
    if max_number:
        elements_to_use = elements[: max_number * 2]
        nb_elements_not_to_use = len(elements[max_number * 2 :])

    nb_elements_to_use = elements_to_use.count()
    nb_elements = nb_elements_to_use + nb_elements_not_to_use
    nb_assigned_tasks = nb_elements_to_use + 1

    num_queries = 13 if element_selection == ELEMENT_SELECTION_ALL else 14
    with django_assert_num_queries(num_queries):
        with CaptureQueriesContext(connection):
            response = user.post(
                reverse("tasks-create", kwargs={"pk": managed_campaign.id}),
                {
                    "type": managed_campaign.project.types.get(name="Page").id,
                    "users": [new_contributor.id, contributor.user.id],
                    "algorithm": algorithm,
                    "element_selection": element_selection,
                    "max_number": max_number,
                    "create_unassigned_tasks": True,
                },
            )
            query_index = 9 if element_selection == ELEMENT_SELECTION_ALL else 10
            query_defining_elements_order = connection.queries[query_index]["sql"]

    managed_campaign.refresh_from_db()
    assert response.status_code == 302
    assert managed_campaign.state == CampaignState.Created
    # If the random algorithm is used alongside with the max_number attribute we can't really know
    # if the already used element was picked in the random queryset and skipped (= one less task)
    total_tasks = Task.objects.count()
    assert total_tasks == nb_elements or total_tasks == nb_elements + 1

    unassigned_tasks = Task.objects.filter(user_tasks__isnull=True)
    # If the random algorithm is used, the element associated to the existing task could have been picked to create an
    # unassigned task that will not be counted by the query just above (since the existing task is assigned to user.user)
    # So we could end up with one less unassigned task than planned in this specific case
    if algorithm == ALGORITHM_RANDOM:
        assert (
            unassigned_tasks.count() == nb_elements_not_to_use or unassigned_tasks.count() == nb_elements_not_to_use - 1
        )
    else:
        assert unassigned_tasks.count() == nb_elements_not_to_use

    assert TaskUser.objects.count() == nb_assigned_tasks
    assert TaskUser.objects.filter(user=contributor.user).count() == math.ceil(nb_elements_to_use / 2)
    assert TaskUser.objects.filter(user=new_contributor).count() == math.floor(nb_elements_to_use / 2)
    # Assert all TaskUser are in draft
    assert TaskUser.objects.filter(state=TaskState.Draft).count() == nb_assigned_tasks

    contributor_elements = list(
        TaskUser.objects.filter(user=contributor.user).order_by("created").values_list("task__element_id")
    )
    new_contributor_elements = list(
        TaskUser.objects.filter(user=new_contributor).order_by("created").values_list("task__element_id")
    )
    sequential_contributor_elements = list(elements_to_use.values_list("id")[: math.ceil(nb_elements_to_use / 2)])
    sequential_user_elements = list(elements_to_use.values_list("id")[math.ceil(nb_elements_to_use / 2) :])
    if algorithm == ALGORITHM_SEQUENTIAL:
        assert contributor_elements == sequential_contributor_elements
        assert new_contributor_elements == sequential_user_elements
        assert (
            'ORDER BY "projects_element"."parent_id" ASC, "projects_element"."order" ASC'
            in query_defining_elements_order
        )
    # Using the random algorithm we can't really assert how tasks were
    # assigned but we can at least check that the proper ordering was used
    if algorithm == ALGORITHM_RANDOM:
        assert "ORDER BY RANDOM() ASC" in query_defining_elements_order

    assert response.url == reverse("admin-campaign-task-list", kwargs={"pk": managed_campaign.id}) + "?state=draft"


@pytest.mark.parametrize("preview_exists", [False, True])
def test_campaign_tasks_generate_preview(user, preview_exists, managed_campaign, django_assert_num_queries):
    elements = managed_campaign.project.elements.filter(image__isnull=False).order_by("parent_id", "order")
    first_element = elements.first()

    if preview_exists:
        TaskUser.objects.create(
            user=user.user,
            task=Task.objects.create(element=first_element, campaign=managed_campaign),
            is_preview=True,
            state=TaskState.Annotated,
        )

    assert Task.objects.count() == preview_exists
    assert TaskUser.objects.count() == preview_exists

    num_queries = 13 if preview_exists else 17
    with django_assert_num_queries(num_queries):
        response = user.post(
            reverse("tasks-create", kwargs={"pk": managed_campaign.id}),
            {
                "type": managed_campaign.project.types.get(name="Page").id,
                "algorithm": ALGORITHM_SEQUENTIAL,
                "element_selection": ELEMENT_SELECTION_ALL,
                "max_number": "",
                "preview": "Preview a single task",
            },
        )

    managed_campaign.refresh_from_db()
    assert response.status_code == 302
    assert managed_campaign.state == CampaignState.Created

    assert Task.objects.count() == 1

    assert TaskUser.objects.count() == 1
    user_task = TaskUser.objects.get()
    assert user_task.user == user.user
    assert user_task.is_preview
    assert user_task.state == TaskState.Annotated if preview_exists else TaskState.Pending
    assert user_task.task.element == first_element

    assert response.url == user_task.annotate_url
