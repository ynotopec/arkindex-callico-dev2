from datetime import timedelta
from time import sleep

import pytest
from pytest_lazy_fixtures import lf as lazy_fixture
from selenium.webdriver.common.by import By


@pytest.mark.parametrize(
    "annotation_endpoint",
    [
        "annotate-transcription",
        "annotate-entity",
        "annotate-entity-form",
        "annotate-elements",
    ],
)
@pytest.mark.parametrize("project", [lazy_fixture("moderated_project")])
def test_annotate_time_spent(page_a1_user_task, build_url, driver, user, force_login, annotation_endpoint):
    """The time spent on any annotation task
    TODO: Test with a classification campaign (requires to be configured)
    """
    assert page_a1_user_task.annotations.count() == 0
    force_login(user)
    driver.get(build_url(annotation_endpoint, pk=page_a1_user_task.id))
    assert driver.title == "Callico - Task annotation"

    submit = driver.find_element(
        By.XPATH,
        '//div[contains(@class, "container")]//form//button[@type="submit"]',
    )

    # Wait 100ms before submitting the annotation (This stays incredibly fast)
    sleep(0.1)
    submit.click()

    assert driver.current_url == build_url("contributor-campaign-task-list", pk=page_a1_user_task.task.campaign_id)
    assert page_a1_user_task.annotations.count() == 1
    annotation = page_a1_user_task.annotations.get()
    assert annotation.version == 1
    assert annotation.duration >= timedelta(milliseconds=100)
    assert annotation.duration < timedelta(seconds=10)
