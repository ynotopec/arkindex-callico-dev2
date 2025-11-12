import hashlib
import os
import uuid

import pytest
import yaml
from arkindex.mock import MockApiClient
from django.contrib.contenttypes.models import ContentType
from django.test import Client

from callico.annotations.models import Task, TaskState, TaskUser
from callico.process.models import Process, ProcessMode, ProcessState
from callico.projects.models import (
    Authority,
    AuthorityValue,
    Campaign,
    CampaignMode,
    CampaignState,
    Element,
    Image,
    Membership,
    Project,
    Provider,
    ProviderType,
    Role,
)
from callico.users.models import User

pytestmark = pytest.mark.django_db

__yaml_cache = {}


@pytest.fixture
def cache_yaml(monkeypatch):
    """
    Cache all calls to yaml.safe_load in order to speedup
    every test cases that load the OpenAPI schema
    """
    # Keep a reference towards the original function
    _original_yaml_load = yaml.safe_load

    def _cached_yaml_load(yaml_payload):
        # Create a unique cache key for direct YAML strings
        # and file descriptors
        if isinstance(yaml_payload, str):
            yaml_payload = yaml_payload.encode("utf-8")
        if isinstance(yaml_payload, bytes):
            key = hashlib.md5(yaml_payload).hexdigest()
        else:
            key = yaml_payload.name

        # Cache result
        if key not in __yaml_cache:
            __yaml_cache[key] = _original_yaml_load(yaml_payload)

        return __yaml_cache[key]

    monkeypatch.setattr(yaml, "safe_load", _cached_yaml_load)


@pytest.fixture(autouse=True)
def setup_environment(responses, settings, cache_yaml):
    """Setup needed environment variables"""

    # Allow accessing remote API schemas
    # defaulting to the prod environment
    schema_url = os.environ.get(
        "ARKINDEX_API_SCHEMA_URL",
        "https://arkindex.teklia.com/api/v1/openapi/?format=json",
    )
    responses.add_passthru(schema_url)

    settings.INSTANCE_URL = "https://callico.test"


@pytest.fixture(autouse=True)
def whitenoise_autorefresh(settings):
    """
    Get rid of whitenoise "No directory at" warning, as it's not helpful when running tests.
    https://github.com/evansd/whitenoise/issues/215#issuecomment-558621213
    """
    settings.WHITENOISE_AUTOREFRESH = True


@pytest.fixture(autouse=True)
def force_english(settings):
    "Force translations to English during tests"
    settings.LANGUAGE_CODE = "en-us"


@pytest.fixture(autouse=True)
def prefetch_contenttypes_for_notifications():
    # We do this to cache the ContentType associated to specific models and prevent two
    # extra queries on a single test (using django-notifications) in the whole test suite
    ContentType.objects.get_for_model(User)
    ContentType.objects.get_for_model(TaskUser)
    ContentType.objects.get_for_model(Campaign)


@pytest.fixture()
def mock_arkindex_client(monkeypatch):
    api_client = MockApiClient()

    def mock_setup(self, *args):
        self.arkindex_client = api_client

    monkeypatch.setattr("callico.process.arkindex.imports.ArkindexProcessBase.setup_arkindex_client", mock_setup)
    return api_client


def _as_client(user=None):
    """
    Return a client to perform requests
    If no user is specified, returns an anonymous client
    The client holds a user attribute to provide the logged user during tests
    """
    client = Client()
    client.user = None
    if user is not None:
        client.force_login(user)
        client.user = user
    return client


@pytest.fixture()
def admin():
    # Using "User.objects.create_superuser()" would add ~0.1s to the setup of each test using this fixture
    return _as_client(User.objects.create(display_name="Root", email="root@callico.org", is_admin=True, is_staff=True))


@pytest.fixture()
def user():
    # Using "User.objects.create_user()" would add ~0.1s to the setup of each test using this fixture
    return _as_client(User.objects.create(display_name="User", email="user@callico.org", is_admin=False))


@pytest.fixture()
def user_with_password(user):
    # "set_password()" is quite heavy to run (see the lighter fixture above) and only needed when testing the login
    user.user.set_password("user")
    user.user.save()
    return user


@pytest.fixture()
def contributor():
    # Using "User.objects.create_user()" would add ~0.1s to the setup of each test using this fixture
    return _as_client(User.objects.create(display_name="Contributor", email="contributor@callico.org", is_admin=False))


@pytest.fixture()
def new_contributor():
    # Using "User.objects.create_user()" would add ~0.1s to the setup of each test using this fixture
    return User.objects.create(display_name="New contributor", email="new@callico.org", is_admin=False)


@pytest.fixture()
def anonymous():
    return _as_client()


@pytest.fixture()
def hidden_project():
    return Project.objects.create(name="Hidden project")


@pytest.fixture()
def hidden_process(hidden_project):
    return hidden_project.processes.create(name="Hidden process")


@pytest.fixture()
def hidden_campaign(hidden_project, user):
    return hidden_project.campaigns.create(
        name="My campaign",
        description="This is a beautiful campaign",
        creator=user.user,
        mode=CampaignMode.Transcription,
        state=CampaignState.Running,
        configuration={"key": "value"},
    )


@pytest.fixture()
def hidden_element(hidden_project, arkindex_provider, image):
    page_type = hidden_project.types.create(name="Page", provider=arkindex_provider, provider_object_id="page")
    return hidden_project.elements.create(
        name="Page 1",
        type=page_type,
        provider=arkindex_provider,
        provider_object_id=str(uuid.uuid4()),
        image=image,
    )


@pytest.fixture()
def public_project():
    return Project.objects.create(name="Public project", public=True)


@pytest.fixture()
def public_process(public_project):
    return public_project.processes.create(name="Public process")


@pytest.fixture()
def moderated_project(user, admin, contributor):
    project = Project.objects.create(name="Moderated project")
    project.memberships.create(user=user.user, role=Role.Moderator)
    project.memberships.create(user=admin.user, role=Role.Moderator)
    project.memberships.create(user=contributor.user, role=Role.Contributor)

    return project


@pytest.fixture()
def moderated_process(moderated_project):
    return moderated_project.processes.create(name="Moderated process")


@pytest.fixture()
def managed_project(user, admin, contributor, arkindex_provider):
    project = Project.objects.create(
        name="Managed project",
        provider=arkindex_provider,
        provider_object_id=str(uuid.uuid4()),
    )
    project.memberships.create(user=user.user, role=Role.Manager)
    project.memberships.create(user=admin.user, role=Role.Manager)
    project.memberships.create(user=contributor.user, role=Role.Contributor)

    return project


@pytest.fixture()
def project(user, admin, contributor, arkindex_provider):
    project = Project.objects.create(
        name="Test project",
        provider=arkindex_provider,
        provider_object_id=str(uuid.uuid4()),
    )
    project.memberships.create(user=user.user, role=Role.Contributor)
    project.memberships.create(user=admin.user, role=Role.Contributor)
    project.memberships.create(user=contributor.user, role=Role.Contributor)

    project.types.create(name="Folder", folder=True, provider=arkindex_provider, provider_object_id="folder")
    project.types.create(name="Volume", provider=arkindex_provider, provider_object_id="volume")
    project.types.create(name="Page", provider=arkindex_provider, provider_object_id="page")
    project.types.create(name="Line", provider=arkindex_provider, provider_object_id="line")

    return project


@pytest.fixture()
def contributed_process(project):
    return project.processes.create(name="Contributed process")


@pytest.fixture()
def public_campaign(user, public_project):
    return public_project.campaigns.create(name="Campaign", creator=user.user, mode=CampaignMode.Transcription)


@pytest.fixture()
def moderated_campaign(user, moderated_project):
    return moderated_project.campaigns.create(name="Campaign", creator=user.user, mode=CampaignMode.Transcription)


@pytest.fixture()
def managed_campaign(user, managed_project, arkindex_provider, image):
    folder_type = managed_project.types.create(
        name="Folder", folder=True, provider=arkindex_provider, provider_object_id="folder"
    )
    page_type = managed_project.types.create(name="Page", provider=arkindex_provider, provider_object_id="page")
    managed_project.types.create(name="Line", provider=arkindex_provider, provider_object_id="line")

    Element.objects.bulk_create(
        Element(
            name=name,
            type=folder_type,
            project=managed_project,
            provider=arkindex_provider,
            provider_object_id=str(uuid.uuid4()),
            order=order,
        )
        for order, name in enumerate(["A", "B", "C", "D"])
    )

    Element.objects.bulk_create(
        Element(
            name=f"Page {i}",
            type=page_type,
            project=managed_project,
            provider=arkindex_provider,
            provider_object_id=str(uuid.uuid4()),
            image=image,
            order=i + 3,
        )
        for i in range(1, 16)
    )

    managed_project.elements.filter(name__in=["B", "C", "Page 3", "Page 4"]).update(
        parent=managed_project.elements.get(name="A")
    )
    managed_project.elements.filter(name__in=["D", "Page 5", "Page 6"]).update(
        parent=managed_project.elements.get(name="B")
    )
    managed_project.elements.filter(name__in=["Page 7"]).update(parent=managed_project.elements.get(name="D"))

    return managed_project.campaigns.create(name="Campaign", creator=user.user, mode=CampaignMode.Transcription)


@pytest.fixture()
def archived_campaign(managed_project, user):
    return managed_project.campaigns.create(
        name="Defunct campaign",
        description="This is an archived campaign",
        creator=user.user,
        mode=CampaignMode.Transcription,
        state=CampaignState.Archived,
        configuration={"key": "value"},
    )


@pytest.fixture()
def public_element(public_project, arkindex_provider, image):
    page_type = public_project.types.create(name="Page", provider=arkindex_provider, provider_object_id="page")
    return public_project.elements.create(
        name="Page 1",
        type=page_type,
        provider=arkindex_provider,
        provider_object_id=str(uuid.uuid4()),
        image=image,
    )


@pytest.fixture()
def moderated_element(moderated_project, arkindex_provider, image):
    page_type = moderated_project.types.create(name="Page", provider=arkindex_provider, provider_object_id="page")
    return moderated_project.elements.create(
        name="Page 1",
        type=page_type,
        provider=arkindex_provider,
        provider_object_id=str(uuid.uuid4()),
        image=image,
    )


@pytest.fixture()
def managed_element(managed_project, arkindex_provider, image):
    page_type = managed_project.types.create(name="Page", provider=arkindex_provider, provider_object_id="page")
    return managed_project.elements.create(
        name="Page 1",
        type=page_type,
        provider=arkindex_provider,
        provider_object_id=str(uuid.uuid4()),
        image=image,
    )


@pytest.fixture()
def managed_campaign_with_tasks(contributor, new_contributor, managed_campaign):
    managed_campaign.project.memberships.create(user=new_contributor, role=Role.Contributor)

    tasks = Task.objects.bulk_create(
        [
            Task(element=element, campaign=managed_campaign)
            for element in managed_campaign.project.elements.filter(image__isnull=False).order_by("name")
        ]
    )
    users_loop = [new_contributor] * (len(tasks) - 1) + [contributor.user] * (len(tasks) - 1)
    states_loop = [state.value for state in TaskState] * (len(tasks) - 1) * 2
    tasks_loop = tasks[1:] * 2
    TaskUser.objects.bulk_create(
        [TaskUser(task=task, user=user, state=state) for user, task, state in zip(users_loop, tasks_loop, states_loop)]
    )

    return managed_campaign


@pytest.fixture()
def campaign(user, project):
    return project.campaigns.create(
        name="My campaign",
        description="This is a beautiful campaign",
        creator=user.user,
        mode=CampaignMode.Transcription,
        state=CampaignState.Created,
        configuration={"key": "value"},
    )


@pytest.fixture()
def page_elements(project, arkindex_provider, image):
    page_type, _created = project.types.get_or_create(name="Page")
    return Element.objects.bulk_create(
        Element(
            name=f"Page {i}",
            type=page_type,
            project=project,
            provider=arkindex_provider,
            provider_object_id=str(uuid.uuid4()),
            image=image,
            order=i + 3,
        )
        for i in range(1, 8)
    )


@pytest.fixture()
def folder_elements(project, arkindex_provider):
    folder_type, _created = project.types.get_or_create(name="Folder", folder=True)
    return Element.objects.bulk_create(
        Element(
            name=name,
            type=folder_type,
            project=project,
            provider=arkindex_provider,
            provider_object_id=str(uuid.uuid4()),
            order=order,
        )
        for order, name in enumerate(["A", "B", "C", "D"])
    )


@pytest.fixture()
def build_architecture(project, page_elements, folder_elements):
    project.elements.filter(name__in=["B", "C", "Page 3", "Page 4"]).update(parent=project.elements.get(name="A"))
    project.elements.filter(name__in=["D", "Page 5", "Page 6"]).update(parent=project.elements.get(name="B"))
    project.elements.filter(name__in=["Page 7"]).update(parent=project.elements.get(name="D"))


@pytest.fixture()
def page_element(page_elements, build_architecture):
    return page_elements[0]


@pytest.fixture()
def folder_element(folder_elements, build_architecture):
    return folder_elements[0]


@pytest.fixture()
def arkindex_provider():
    return Provider.objects.create(
        name="Arkindex test",
        type=ProviderType.Arkindex,
        api_url="https://arkindex.teklia.com/api/v1",
        api_token="123456789",
        extra_information={"worker_run_publication": "c0f3c0f3-c0f3-c0f3-c0f3-c0f3c0f3c0f3"},
    )


@pytest.fixture()
def iiif_provider():
    return Provider.objects.create(
        name="IIIF test",
        type=ProviderType.IIIF,
        api_url="https://iiif.teklia.com/api/v1",
        api_token="123456789",
    )


@pytest.fixture()
def image():
    return Image.objects.create(iiif_url="http://iiif/url", width=42, height=666)


@pytest.fixture()
def projects(user, admin):
    users_loop = [user.user] * 3 + [admin.user] * 3
    roles_loop = [Role.Contributor, Role.Moderator, Role.Manager] * 2
    Membership.objects.bulk_create(
        [
            Membership(user=users_loop[i], role=roles_loop[i], project=Project.objects.create(name=f"Project {i+1}"))
            for i in range(0, 6)
        ]
    )

    Project.objects.create(name="Public project", public=True)

    Project.objects.create(name="Hidden project")

    return Project.objects.all()


@pytest.fixture()
def campaigns(projects, user):
    for project in projects:
        Campaign.objects.bulk_create(
            [
                Campaign(
                    project=project,
                    name=f"Campaign {state}",
                    description="This is a beautiful campaign",
                    creator=user.user,
                    mode=CampaignMode.Transcription,
                    state=state,
                    configuration={"key": "value"},
                )
                for state in CampaignState
            ]
        )

    return Campaign.objects.all()


@pytest.fixture()
def tasks(campaigns, page_element, user, admin):
    tasks = Task.objects.bulk_create([Task(element=page_element, campaign=campaign) for campaign in campaigns])
    users_loop = [user.user] * len(tasks) + [admin.user] * len(tasks)
    return TaskUser.objects.bulk_create(
        [TaskUser(task=task, user=user, state=TaskState.Pending) for user, task in zip(users_loop, tasks * 2)]
    )


@pytest.fixture()
def processes(managed_project, user, admin):
    users = [user.user, admin.user]
    return Process.objects.bulk_create(
        [
            Process(
                name=f"{state.capitalize()} process",
                mode=list(ProcessMode)[index % len(ProcessMode)],
                state=state,
                configuration={},
                project=managed_project,
                creator=users[index % len(users)],
            )
            for index, state in enumerate(ProcessState)
        ]
    )


@pytest.fixture()
def process(processes):
    return processes[0]


@pytest.fixture()
def process_with_celery_mock(mocker, process):
    celery_mock = mocker.patch("celery.app.task.Task.request")
    celery_mock.id = str(process.id)
    return process


@pytest.fixture()
def authority():
    authority = Authority.objects.create(name="A few countries")
    AuthorityValue.objects.bulk_create(
        AuthorityValue(
            authority=authority,
            authority_value_id=f"C{index}#",
            value=country,
        )
        for index, country in enumerate(["Belgium", "France", "Germany", "Italy", "Spain"], start=1)
    )
    return authority
