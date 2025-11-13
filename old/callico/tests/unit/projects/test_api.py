import uuid

import pytest
from django.urls import reverse
from pytest_lazy_fixtures import lf as lazy_fixture
from rest_framework import status

pytestmark = pytest.mark.django_db


def test_list_projects_requires_login(anonymous):
    response = anonymous.get(reverse("list-projects"))
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {"detail": "Authentication credentials were not provided."}


def test_list_projects_forbidden(user):
    response = user.get(reverse("list-projects"))
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {"detail": "You do not have permission to perform this action."}


def test_list_projects(admin, hidden_project, public_project, managed_project):
    response = admin.get(reverse("list-projects"))
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data == [
        {
            "id": str(hidden_project.id),
            "name": "Hidden project",
            "public": False,
            "provider": None,
            "provider_object_id": hidden_project.provider_object_id,
        },
        {
            "id": str(managed_project.id),
            "name": "Managed project",
            "public": False,
            "provider": {"name": "Arkindex test", "type": "Arkindex"},
            "provider_object_id": managed_project.provider_object_id,
        },
        {
            "id": str(public_project.id),
            "name": "Public project",
            "public": True,
            "provider": None,
            "provider_object_id": public_project.provider_object_id,
        },
    ]


def test_retrieve_element_wrong_element_id(user):
    response = user.get(reverse("retrieve-element", kwargs={"pk": "cafecafe-cafe-cafe-cafe-cafecafecafe"}))
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {"detail": "No Element matches the given query."}


@pytest.mark.parametrize("is_folder", [True, False])
def test_retrieve_element_requires_login(anonymous, public_element, is_folder):
    if is_folder:
        public_element.image = None
        public_element.save()

    response = anonymous.get(reverse("retrieve-element", kwargs={"pk": public_element.id}))
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {"detail": "Authentication credentials were not provided."}


@pytest.mark.parametrize("is_folder", [True, False])
@pytest.mark.parametrize("has_children", [True, False])
@pytest.mark.parametrize("client, forbidden", [(lazy_fixture("user"), True), (lazy_fixture("admin"), False)])
def test_retrieve_hidden_element(client, forbidden, hidden_element, is_folder, has_children):
    if has_children:
        line_type = hidden_element.project.types.create(name="Line")
        child_element = hidden_element.project.elements.create(
            name="Line x",
            type=line_type,
            provider=hidden_element.provider,
            provider_object_id=str(uuid.uuid4()),
            image=hidden_element.image,
            polygon=[[1, 1], [2, 2], [3, 3]],
            parent_id=hidden_element.id,
        )

    if is_folder:
        hidden_element.image = None
        hidden_element.save()

    response = client.get(reverse("retrieve-element", kwargs={"pk": hidden_element.id}))

    if forbidden:
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.json() == {"detail": "You do not have permission to perform this action."}
    else:
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data == {
            "id": str(hidden_element.id),
            "name": hidden_element.name,
            "polygon": hidden_element.polygon,
            "image": (
                {
                    "url": hidden_element.image.iiif_url,
                    "width": hidden_element.image.width,
                    "height": hidden_element.image.height,
                }
                if not is_folder
                else None
            ),
            "parent_id": hidden_element.parent_id,
            "children": [
                {
                    "id": str(child_element.id),
                    "name": child_element.name,
                    "polygon": child_element.polygon,
                    "image": {
                        "url": child_element.image.iiif_url,
                        "width": child_element.image.width,
                        "height": child_element.image.height,
                    },
                }
            ]
            if has_children
            else [],
        }


@pytest.mark.parametrize(
    "private_element",
    [
        lazy_fixture("page_element"),
        lazy_fixture("moderated_element"),
        lazy_fixture("managed_element"),
    ],
)
@pytest.mark.parametrize("is_folder", [True, False])
@pytest.mark.parametrize("has_children", [True, False])
def test_retrieve_private_element(user, admin, private_element, is_folder, has_children):
    private_element.project.memberships.filter(user=admin.user).delete()

    if has_children:
        line_type, _created = private_element.project.types.get_or_create(name="Line")
        child_element = private_element.project.elements.create(
            name="Line x",
            type=line_type,
            provider=private_element.provider,
            provider_object_id=str(uuid.uuid4()),
            image=private_element.image,
            polygon=[[1, 1], [2, 2], [3, 3]],
            parent_id=private_element.id,
        )

    if is_folder:
        private_element.image = None
        private_element.save()

    response = user.get(reverse("retrieve-element", kwargs={"pk": private_element.id}))

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data == {
        "id": str(private_element.id),
        "name": private_element.name,
        "polygon": private_element.polygon,
        "image": (
            {
                "url": private_element.image.iiif_url,
                "width": private_element.image.width,
                "height": private_element.image.height,
            }
            if not is_folder
            else None
        ),
        "parent_id": private_element.parent_id,
        "children": [
            {
                "id": str(child_element.id),
                "name": child_element.name,
                "polygon": child_element.polygon,
                "image": {
                    "url": child_element.image.iiif_url,
                    "width": child_element.image.width,
                    "height": child_element.image.height,
                },
            }
        ]
        if has_children
        else [],
    }


@pytest.mark.parametrize("is_folder", [True, False])
@pytest.mark.parametrize("has_children", [True, False])
def test_retrieve_public_element(user, public_element, is_folder, has_children):
    if has_children:
        line_type = public_element.project.types.create(name="Line")
        child_element = public_element.project.elements.create(
            name="Line x",
            type=line_type,
            provider=public_element.provider,
            provider_object_id=str(uuid.uuid4()),
            image=public_element.image,
            polygon=[[1, 1], [2, 2], [3, 3]],
            parent_id=public_element.id,
        )

    if is_folder:
        public_element.image = None
        public_element.save()

    response = user.get(reverse("retrieve-element", kwargs={"pk": public_element.id}))

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data == {
        "id": str(public_element.id),
        "name": public_element.name,
        "polygon": public_element.polygon,
        "image": (
            {
                "url": public_element.image.iiif_url,
                "width": public_element.image.width,
                "height": public_element.image.height,
            }
            if not is_folder
            else None
        ),
        "parent_id": public_element.parent_id,
        "children": [
            {
                "id": str(child_element.id),
                "name": child_element.name,
                "polygon": child_element.polygon,
                "image": {
                    "url": child_element.image.iiif_url,
                    "width": child_element.image.width,
                    "height": child_element.image.height,
                },
            }
        ]
        if has_children
        else [],
    }


def test_list_authority_values_wrong_authority_id(user):
    response = user.get(reverse("list-authority-values", kwargs={"pk": "cafecafe-cafe-cafe-cafe-cafecafecafe"}))
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {"detail": "No Authority matches the given query."}


def test_list_authority_values_requires_login(anonymous, authority):
    response = anonymous.get(reverse("list-authority-values", kwargs={"pk": authority.id}))
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json() == {"detail": "Authentication credentials were not provided."}


def test_list_authority_values(user, authority):
    response = user.get(reverse("list-authority-values", kwargs={"pk": authority.id}))
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data == [
        {
            "value": "Belgium",
        },
        {
            "value": "France",
        },
        {
            "value": "Germany",
        },
        {
            "value": "Italy",
        },
        {
            "value": "Spain",
        },
    ]


@pytest.mark.parametrize(
    "search, results",
    [
        (
            "g",
            [
                {
                    "value": "Belgium",
                },
                {
                    "value": "Germany",
                },
            ],
        ),
        (
            "C2#",
            [
                {
                    "value": "France",
                },
            ],
        ),
    ],
)
def test_list_authority_values_with_search(search, results, user, authority):
    response = user.get(reverse("list-authority-values", kwargs={"pk": authority.id}) + f"?search={search}")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data == results
