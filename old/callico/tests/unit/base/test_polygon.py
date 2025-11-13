import re

import pytest
from django.core.exceptions import ValidationError

from callico.base.fields import PolygonField


@pytest.mark.parametrize(
    "polygon",
    [
        [[-1, 2], [2, -3], [-3, 4]],
        [[1, 2], [1, 2], [2, 3]],
    ],
)
def test_invalid_polygon(polygon):
    with pytest.raises(
        ValidationError, match=re.escape("['Polygon field must be a list of at least 3 positive integer couples']")
    ):
        PolygonField().get_prep_value(polygon)
        PolygonField().run_validators(polygon)
