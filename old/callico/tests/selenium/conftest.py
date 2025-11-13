import os
import uuid
from urllib.parse import urlencode, urljoin

import pytest
from django.test import Client
from django.urls import reverse
from selenium import webdriver
from urllib3.exceptions import RequestError

from callico.annotations.models import TaskState
from callico.projects.models import CampaignMode, CampaignState, Element, Image, Project, Provider, ProviderType, Role
from callico.users.models import User

pytestmark = pytest.mark.django_db

WEBDRIVER_KWARGS = {
    "chrome": {"options": webdriver.ChromeOptions()},
    "firefox": {"options": webdriver.FirefoxOptions()},
}

# Hostname of the webserver
SELENIUM_HOST = os.environ.get("SELENIUM_HOST", "localhost")
# Selenium grid URL
SELENIUM_URL = f"http://{SELENIUM_HOST}:4444/wd/hub"
# Name of the live server host
LIVE_SERVER_HOST = os.environ.get("DJANGO_LIVE_TEST_SERVER_ADDRESS", "localhost")

# Timeout for loaded pages, is seconds
HTTP_TIMEOUT = 5


@pytest.fixture(scope="session")
def _base_driver():
    """Builds and destroys a browser session for all tests.
    This fixture establishes a connection to the webdriver through the Selenium grid service.
    """
    driver_name = os.environ.get("SELENIUM_BROWSER", None)
    driver_kwargs = WEBDRIVER_KWARGS.get(driver_name)

    if driver_name is None or driver_kwargs is None:
        choices = ", ".join(WEBDRIVER_KWARGS)
        pytest.exit(
            "SELENIUM_BROWSER variable must be defined to run tests with Selenium.\n" f"Available choices: {choices}."
        )

    try:
        driver = webdriver.Remote(
            command_executor=SELENIUM_URL,
            **driver_kwargs,
        )
    except RequestError as e:
        pytest.exit(
            f"Webdriver could not be reached at {SELENIUM_URL}: {e}.\n"
            "Please ensure that Selenium grid is running.\n"
            "You can start a standalone webdriver using `docker run -p 4444:4444 selenium/standalone-<driver>:4.6.0`"
        )
    yield driver
    driver.quit()


@pytest.fixture
def driver(_base_driver, build_url, user):
    """Creates a clean environment for each test within the same Selenium session.
    Cleans all existing tabs and session data.
    """
    _base_driver.delete_all_cookies()
    # Create a new window and keep its reference
    _base_driver.switch_to.new_window("tab")
    new_tab = _base_driver.current_window_handle

    # Close all opened windows except the clean one
    for window_handle in _base_driver.window_handles:
        if window_handle != new_tab:
            _base_driver.switch_to.window(window_handle)
            _base_driver.close()

    _base_driver.switch_to.window(new_tab)
    return _base_driver


@pytest.fixture
def build_url(live_server):
    """Returns a helper method to build URLs on the Callico test server.
    The helper takes a route name, optional keyword arguments for
    the `django.urls.reverse` method and optional GET parameters.
    """

    def _url(endpoint, query_params={}, **kwargs):
        path = reverse(endpoint, kwargs=kwargs)
        if query_params:
            path = "?".join((path, urlencode(query_params, safe="/")))
        return urljoin(live_server.url, path)

    return _url


@pytest.fixture(scope="function")
def user(django_db_setup, django_db_blocker):
    """Generate a user in the DB initial fixture"""
    with django_db_blocker.unblock():
        user = User.objects.create_user(display_name="User", email="user@callico.org", password="secretPassword")
    return user


@pytest.fixture(scope="function")
def admin(django_db_setup, django_db_blocker):
    """Generate an admin user in the DB initial fixture"""
    with django_db_blocker.unblock():
        admin = User.objects.create(display_name="Root", email="root@callico", is_admin=True)
    return admin


@pytest.fixture
def force_login(driver, build_url):
    """Returns a helper method to log in an user to Callico by setting its session cookies"""

    def _login(user):
        driver.get(build_url("login"))
        client = Client()
        client.force_login(user)
        for name, cookie in client.cookies.items():
            driver.add_cookie({"name": name, "value": cookie.value})

    return _login


@pytest.fixture()
def arkindex_provider():
    return Provider.objects.create(
        name="Arkindex test",
        type=ProviderType.Arkindex,
        api_url="https://arkindex.teklia.com/api/v1",
        api_token="123456789",
    )


@pytest.fixture()
def image():
    return Image.objects.create(iiif_url="http://iiif/url", width=42, height=666)


@pytest.fixture
def public_project(admin):
    return Project.objects.create(name="Public project", public=True)


@pytest.fixture
def moderated_project(user, admin):
    project = Project.objects.create(name="Moderated project", public=False)
    project.memberships.create(user=admin, role=Role.Moderator)
    project.memberships.create(user=user, role=Role.Contributor)
    return project


@pytest.fixture
def managed_project(user, admin):
    project = Project.objects.create(name="Managed project", public=False)
    project.memberships.create(user=admin, role=Role.Manager)
    project.memberships.create(user=user, role=Role.Contributor)
    return project


@pytest.fixture
def project_elements(project, arkindex_provider, image):
    """    Project
         /          \
     Folder A     Folder B
        |         /     \
     Page A1  Page B2  Page B3
    """

    folder_type = project.types.create(
        name="Folder", folder=True, provider=arkindex_provider, provider_object_id="folder"
    )
    page_type = project.types.create(name="Page", provider=arkindex_provider, provider_object_id="page")
    folder_a, folder_b = Element.objects.bulk_create(
        Element(
            name=name,
            type=folder_type,
            project=project,
            provider=arkindex_provider,
            provider_object_id=uuid.uuid4(),
            order=idx,
        )
        for idx, name in enumerate(("Folder A", "Folder B"))
    )
    Element.objects.bulk_create(
        Element(
            name=name,
            type=page_type,
            project=project,
            provider=arkindex_provider,
            provider_object_id=uuid.uuid4(),
            image=image,
            parent=parent,
            order=idx,
        )
        for idx, name, parent in (
            (1, "Page A1", folder_a),
            (1, "Page B1", folder_b),
            (2, "Page B2", folder_b),
        )
    )
    return project.elements.all()


@pytest.fixture
def campaign(project, admin):
    return project.campaigns.create(
        name="Moderated campaign",
        description="A beautiful campaign",
        creator=admin,
        mode=CampaignMode.Transcription,
        state=CampaignState.Running,
        configuration={"key": "value"},
    )


@pytest.fixture
def page_a1_user_task(campaign, user, project_elements):
    page_a1 = project_elements.get(name="Page A1")
    task = campaign.tasks.create(element=page_a1)
    return task.user_tasks.create(user=user, state=TaskState.Pending)
