import pytest
from pytest_lazy_fixtures import lf as lazy_fixture

from callico.projects.utils import bounding_box, build_iiif_url

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "arg, kwargs, expected_error",
    [
        (None, {}, "image attribute shouldn't be null and should be of type projects.Image"),
        ("wrong_image", {}, "image attribute shouldn't be null and should be of type projects.Image"),
        (
            lazy_fixture("image"),
            {"size_max_width": "aaa"},
            "size_max_width attribute should be null or of type int",
        ),
        (
            lazy_fixture("image"),
            {"size_max_height": "aaa"},
            "size_max_height attribute should be null or of type int",
        ),
        (
            lazy_fixture("image"),
            {"x": None},
            "x attribute shouldn't be null and should be of type int",
        ),
        (
            lazy_fixture("image"),
            {"x": "full"},
            "x attribute shouldn't be null and should be of type int",
        ),
        (
            lazy_fixture("image"),
            {"y": None},
            "y attribute shouldn't be null and should be of type int",
        ),
        (
            lazy_fixture("image"),
            {"y": "full"},
            "y attribute shouldn't be null and should be of type int",
        ),
        (
            lazy_fixture("image"),
            {"width": "full"},
            "width attribute shouldn't be null and should be of type int",
        ),
        (
            lazy_fixture("image"),
            {"height": "full"},
            "height attribute shouldn't be null and should be of type int",
        ),
    ],
)
def test_build_iiif_url_wrong_params(arg, kwargs, expected_error):
    with pytest.raises(AssertionError) as e:
        build_iiif_url(arg, **kwargs)
    assert str(e.value) == expected_error


@pytest.mark.parametrize(
    "kwargs, expected_url",
    [
        ({}, "http://iiif/url/0,0,42,666/max/0/default.jpg"),
        # Size max with is limited to the real size of the image
        ({"size_max_width": 400}, "http://iiif/url/0,0,42,666/42,/0/default.jpg"),
        ({"size_max_width": 30, "size_max_height": 300}, "http://iiif/url/0,0,42,666/30,300/0/default.jpg"),
        ({"x": 8}, "http://iiif/url/8,0,42,666/max/0/default.jpg"),
        ({"y": 8}, "http://iiif/url/0,8,42,666/max/0/default.jpg"),
        ({"width": 8}, "http://iiif/url/0,0,8,666/max/0/default.jpg"),
        ({"height": 8}, "http://iiif/url/0,0,42,8/max/0/default.jpg"),
    ],
)
def test_build_iiif_url(image, kwargs, expected_url):
    assert build_iiif_url(image, **kwargs) == expected_url


def test_build_iiif_url_trailing_slash(image):
    image.iiif_url = image.iiif_url + "/"
    image.save()
    assert build_iiif_url(image) == "http://iiif/url/0,0,42,666/max/0/default.jpg"


def test_bounding_box():
    not_rectangle = [(0, 0), (1000, 0), (500, 500), (1000, 1000), (0, 1000), (0, 0)]
    assert bounding_box(not_rectangle) == (0, 0, 1000, 1000)
