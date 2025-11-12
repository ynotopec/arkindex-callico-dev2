# from selenium.webdriver.common.keys import Keys
import pytest
from pytest_lazy_fixtures import lf as lazy_fixture
from selenium.webdriver.common.by import By

from callico.projects.models import Project

pytestmark = pytest.mark.django_db

PROJECTS_XPATH = '//div[contains(@class, "container")]/div[contains(@class, "columns")]/div[contains(@class, "column")]'
BROWSE_ELEMENTS_XPATH = (
    '//div[contains(@class, "container")]/div[contains(@class, "columns")]/div/div/div/a/div[contains(@class, "card")]'
)


def test_list_projects_anonymous(build_url, driver, public_project, moderated_project):
    """An anonymous user can only list public projects"""
    Project.objects.create(name="Second public project", public=True)

    driver.get(build_url("projects"))
    assert driver.title == "Callico - Projects"
    assert driver.current_url == build_url("projects")

    projects = driver.find_elements(By.XPATH, PROJECTS_XPATH)
    assert [getattr(project.find_element(By.CLASS_NAME, "is-size-4"), "text", "") for project in projects] == [
        "Public project",
        "Second public project",
    ]


def test_list_private_projects(build_url, driver, user, force_login, public_project, moderated_project):
    """A user can list private projects they are a member on"""
    force_login(user)
    driver.get(build_url("projects"))
    assert driver.current_url == build_url("projects")
    assert driver.title == "Callico - Projects"
    projects = driver.find_elements(By.XPATH, PROJECTS_XPATH)
    assert [getattr(project.find_element(By.CLASS_NAME, "is-size-4"), "text", "") for project in projects] == [
        "Moderated project"
    ]


def test_list_public_projects(build_url, driver, user, force_login, public_project, moderated_project):
    """A user can list public projects on a separate tab"""
    Project.objects.create(name="Second public project", public=True)

    force_login(user)
    driver.get(build_url("projects"))
    assert driver.title == "Callico - Projects"
    assert driver.current_url == build_url("projects")

    # User must click on the "Public projects" tab
    public_tab = driver.find_element(
        By.XPATH,
        '//div[contains(@class, "container")]/div[contains(@class, "tabs")]//a[@href="?public=True"]',
    )
    public_tab.click()
    assert driver.current_url == build_url("projects", query_params={"public": True})

    projects = driver.find_elements(By.XPATH, PROJECTS_XPATH)
    assert [getattr(project.find_element(By.CLASS_NAME, "is-size-4"), "text", "") for project in projects] == [
        "Public project",
        "Second public project",
    ]


@pytest.mark.parametrize("project", [lazy_fixture("moderated_project"), lazy_fixture("managed_project")])
def test_project_browse(build_url, driver, admin, force_login, project, project_elements):
    """A moderator/manager can browse a project and see its elements recursively"""
    force_login(admin)
    driver.get(build_url("project-browse", project_id=project.id))
    # User can browse root elements of a project
    assert driver.title == "Callico - Browse elements"
    assert driver.current_url == build_url("project-browse", project_id=project.id)

    folders = driver.find_elements(By.XPATH, BROWSE_ELEMENTS_XPATH)
    assert len(folders) == 2
    assert [getattr(folder.find_element(By.CLASS_NAME, "content"), "text", "") for folder in folders] == [
        "Folder A\nType: Folder",
        "Folder B\nType: Folder",
    ]

    # User can navigate inside folder B and browse pages
    folder = folders[1]
    folder.click()
    folder_obj = project_elements.get(name="Folder B")
    assert driver.current_url == build_url(
        "project-browse",
        project_id=str(project.id),
        element_id=folder_obj.id,
    )
    pages = driver.find_elements(By.XPATH, BROWSE_ELEMENTS_XPATH)
    assert len(pages) == 2
    assert [getattr(page.find_element(By.CLASS_NAME, "content"), "text", "") for page in pages] == [
        "Page B1\nType: Page",
        "Page B2\nType: Page",
    ]

    # User may display details of a page
    page = pages[0]
    page_obj = project_elements.get(name="Page B1")
    page.click()
    assert driver.title == "Callico - Element details"
    assert driver.current_url == build_url("element-details", pk=page_obj.pk)
