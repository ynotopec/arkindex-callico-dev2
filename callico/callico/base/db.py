from django.db.models import Aggregate, FloatField


class Median(Aggregate):
    """Compute the median value using the percentile_cont function in PostgreSQL"""

    def __init__(self, expression, output_field=FloatField, **kwargs):
        super().__init__(expression, **kwargs)
        self.name = "median"
        self.output_field = output_field()
        self.template = "percentile_cont(0.5) WITHIN GROUP (ORDER BY %(expressions)s)"
