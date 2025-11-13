import pytest
from selenium.webdriver.common.by import By

pytestmark = pytest.mark.django_db


def test_login(build_url, driver, user):
    """An anonymous user can log in to Callico and is redirected to the projects list"""
    driver.get(build_url("login"))
    username_field = driver.find_element(By.ID, "id_username")
    pwd_field = driver.find_element(By.ID, "id_password")
    submit = driver.find_element(By.XPATH, '//form/button[@value="login"]')

    username_field.send_keys("user@callico.org")
    pwd_field.send_keys("secretPassword")
    submit.click()

    assert driver.current_url == build_url("projects")
    assert driver.title == "Callico - Projects"
