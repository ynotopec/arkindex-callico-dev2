from itertools import groupby

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _


def validate_polygon(value):
    "Ensure polygon is a list of at least 3 valid coordinates"

    def is_coord(coords):
        return isinstance(coords, list) and len(coords) == 2 and all(isinstance(pt, int) and pt >= 0 for pt in coords)

    if not isinstance(value, list) or len(value) < 3 or not all(is_coord(item) for item in value):
        raise ValidationError(_("Polygon field must be a list of at least 3 positive integer couples"))


class PolygonField(models.JSONField):
    "A JSON field allowing only lists of integers coordinates"

    default_validators = [validate_polygon]
    help_text = _("A polygon constituted of couples of points: [[x1, y1], [x2, y2], [x3, y3]].")

    def get_prep_value(self, value):
        if not value:
            return None
        # Deduplicate polygons
        value = [dupes[0] for dupes in groupby(value)]
        if len(value) < 3:
            raise ValidationError(_("Polygon field must be a list of at least 3 positive integer couples"))
        # Re-ordering the polygon is complex, just ensure the lowest coordinate is placed first
        min_index = value.index(min(value))
        return super().get_prep_value(value[min_index:] + value[:min_index])
