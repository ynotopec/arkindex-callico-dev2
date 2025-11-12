ENTITY_FORM_GROUP_MODE = "group"


def build_iiif_url(image, size_max_width=None, size_max_height=None, x=0, y=0, width=None, height=None):
    """
    Size max width and height are converted according to IIIF 2 specification .
    https://iiif.io/api/image/2.1/#size
    Examples:
    width=None,height=None → 'max'
    width=100,height=None → '100,'
    width=None,height=200 → ',200'
    """
    from callico.projects.models import Image

    assert image and isinstance(image, Image), "image attribute shouldn't be null and should be of type projects.Image"
    assert x is not None and isinstance(x, int), "x attribute shouldn't be null and should be of type int"
    assert y is not None and isinstance(y, int), "y attribute shouldn't be null and should be of type int"
    assert size_max_width is None or isinstance(
        size_max_width, int
    ), "size_max_width attribute should be null or of type int"
    assert size_max_height is None or isinstance(
        size_max_height, int
    ), "size_max_height attribute should be null or of type int"

    if not width:
        width = image.width
    if not height:
        height = image.height

    assert width is not None and isinstance(width, int), "width attribute shouldn't be null and should be of type int"
    assert height is not None and isinstance(
        height, int
    ), "height attribute shouldn't be null and should be of type int"

    if (size_max_width, size_max_height) == (None, None):
        size = "max"
    else:
        # Build size parameter, but avoid exceeding zone's maximum real size
        # https://gitlab.teklia.com/callico/callico/-/issues/414
        size_width = "" if size_max_width is None else min(size_max_width, width)
        size_height = "" if size_max_height is None else min(size_max_height, height)
        size = f"{size_width},{size_height}"

    return f"{image.iiif_url.rstrip('/')}/{x},{y},{width},{height}/{size}/0/default.jpg"


def bounding_box(polygon):
    """
    Returns a 4-tuple (x, y, width, height) for the bounding box of a polygon
    """
    all_x, all_y = zip(*polygon)
    x, y = min(all_x), min(all_y)
    width, height = max(all_x) - x, max(all_y) - y
    return int(x), int(y), int(width), int(height)


def flatten_campaign_fields(campaign):
    flattened = []
    for field in campaign.configuration.get("fields", []):
        flattened.extend(
            [(field["legend"], subfield) for subfield in field.get("fields", [])]
            if field.get("mode") == ENTITY_FORM_GROUP_MODE
            else [("", field)]
        )

    return flattened


def get_campaign_field_groups(campaign):
    return [
        (index, field)
        for index, field in enumerate(campaign.configuration.get("fields", []))
        if field.get("mode") == ENTITY_FORM_GROUP_MODE
    ]


def find_configured_sorted_field(configuration, entity_type, instruction):
    return next(
        field
        for field in configuration
        if field.get("entity_type") == entity_type and field.get("instruction") == instruction
    )


def find_configured_sorted_group(configuration, legend):
    return next(field for field in configuration if field.get("legend") == legend)
