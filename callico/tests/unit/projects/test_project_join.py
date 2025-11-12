import pytest
from django.contrib import messages
from django.urls import reverse

from callico.projects.models import Membership, Role

pytestmark = pytest.mark.django_db


def test_project_join_anonymous(anonymous, project):
    "An anonymous user is redirected to the login page"
    join_url = reverse("project-join", kwargs={"invite_token": project.invite_token})

    response = anonymous.get(join_url)
    assert response.status_code == 302
    assert response.url == reverse("login") + f"?next={join_url}"


def test_project_join_wrong_project_invite_token(user):
    join_url = reverse("project-join", kwargs={"invite_token": "not_a_real_token"})

    response = user.get(join_url)
    assert response.status_code == 302
    assert response.url == reverse("projects")

    assert [(msg.level, msg.message) for msg in messages.get_messages(response.wsgi_request)] == [
        (
            messages.ERROR,
            "The invite link you followed doesn't match any registered project, it might be expired, please contact the manager who provided it.",
        ),
    ]


def test_project_join_already_member(user, project):
    assert project.memberships.filter(user_id=user.user.id).exists()

    join_url = reverse("project-join", kwargs={"invite_token": project.invite_token})

    response = user.get(join_url)
    assert response.status_code == 302
    assert response.url == reverse("project-details", kwargs={"project_id": project.id})

    assert [(msg.level, msg.message) for msg in messages.get_messages(response.wsgi_request)] == [
        (
            messages.INFO,
            "You clicked on an invitation link to join this project but you already are one of its member.",
        ),
    ]


def test_project_join_get(user, project, django_assert_num_queries):
    Membership.objects.filter(project=project, user=user.user).delete()
    assert not project.memberships.filter(user=user.user).exists()

    with django_assert_num_queries(5):
        response = user.get(reverse("project-join", kwargs={"invite_token": project.invite_token}))
    assert response.status_code == 200
    assert response.context["project"] == project


def test_project_join_post(user, project, django_assert_num_queries):
    Membership.objects.filter(project=project, user=user.user).delete()
    assert not project.memberships.filter(user=user.user).exists()

    with django_assert_num_queries(6):
        response = user.post(reverse("project-join", kwargs={"invite_token": project.invite_token}))
    assert response.status_code == 302
    assert project.memberships.filter(user=user.user, role=Role.Contributor).exists()

    assert response.url == reverse("project-details", kwargs={"project_id": project.id})

    assert [(msg.level, msg.message) for msg in messages.get_messages(response.wsgi_request)] == [
        (messages.SUCCESS, "You have joined the project as a contributor."),
    ]
