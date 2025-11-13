from django.template.defaulttags import WidthRatioNode

# This will make sure the app is always imported when
# Django starts so that shared_task will use this app.
from .celery import app as celery_app

__all__ = ("celery_app",)

# Retrieving the default renderer of `widthratio` template tag
widthratio_render = WidthRatioNode.render


def custom_widthratio_render(cls, context):
    """In our templates, we often use the `widthratio` tag from Django to display progress bars.
    Documentation: https://docs.djangoproject.com/en/5.0/ref/templates/builtins/#widthratio

    This template tag calculates a ratio between the current value `value` and the maximum value
    `max_value` and applies it to a constant named `max_width`.
      - e.g.: Using {% widthratio 4 10 100 %}, we would end up with 4/10*100 = 0.4*100 = 40.

    When displaying progress bars, we want to round the `widthratio` output with a clean approximation.
    If `value` is at least 1, we should not output a ratio equal to 0.
    If `value` is less than `max_value`, we should not output a ratio equal to `max_width`.
    Otherwise, we should calculate the ratio as defined in
    https://github.com/django/django/blob/main/django/template/defaulttags.py#L502.

    Thus, this function helps patching the `widthratio` tag renderer with our custom behavior. We
    expect `widthratio` to be called with an **as** variable named "*percentage*".
    If both constraints are met, we patch the original renderer with our custom logic which updates
    the **as** variable `context[cls.asvar]` using the clean approximation described above.

    In our case, the `widthratio` tag helps us to calculate the `width` percentage (CSS style)
    that should be applied to the tasks progress bar. Here are examples with outputs from the
    original renderer (ORIG) and our custom one (CUST).
      - e.g.: 0 completed tasks out of 500 => 0% completed (ORIG) / 0% completed (CUST)
              1                            => 0% completed (ORIG) / 1% completed (CUST)
              250                          => 50% completed (ORIG) / 50% completed (CUST)
              499                          => 100% completed (ORIG) / 99% completed (CUST)
              500                          => 100% completed (ORIG) / 100% completed (CUST)
    """
    output = widthratio_render(cls, context)
    # Patching the renderer when `widthratio` has an **as** variable name containing the "percentage" string
    if not cls.asvar or "percentage" not in cls.asvar:
        return output

    # When using **as**, the widthratio output is stored in `context[cls.asvar]`
    asvar_output = int(context[cls.asvar])

    # Retrieving cleaned parameters passed to the `widthratio` tag
    value = int(cls.val_expr.resolve(context))
    max_value = int(cls.max_expr.resolve(context))
    max_width = int(cls.max_width.resolve(context))

    # `value` is a bit less than `max_value`, the output should not equal `max_width`
    if asvar_output == max_width and value != max_value:
        context[cls.asvar] = str(max_width - 1)
    # `value` is not zero, the output should not equal `0` either
    elif asvar_output == 0 and value != 0:
        context[cls.asvar] = "1"

    # Returning the original output as the real one is stored in `context[cls.asvar]` anyway
    return output


# Overriding the default renderer of `widthratio` template tag
WidthRatioNode.render = custom_widthratio_render
