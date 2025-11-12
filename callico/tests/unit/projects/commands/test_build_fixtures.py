import logging

import pytest
from django.core.management import call_command
from django.db.models import Count

from callico.annotations.models import Task, TaskUser
from callico.projects.models import Campaign, Class, Element, Membership, Project, Type
from callico.users.models import User

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("run_twice", [False, True])
def test_build_fixtures(run_twice, caplog):
    call_command("build_fixtures")

    if run_twice:
        call_command("build_fixtures")
        for log_message in [
            (
                logging.WARNING,
                "Project Private project no users already exists.",
            ),
            (
                logging.WARNING,
                "Project HORAE with users already exists. Skipping…",
            ),
            (
                logging.WARNING,
                "Project HORAE no users already exists. Skipping…",
            ),
            (
                logging.WARNING,
                "Project Socface with users already exists. Skipping…",
            ),
            (
                logging.WARNING,
                "Project Esposalles with users already exists. Skipping…",
            ),
        ]:
            assert log_message in [(level, message) for _module, level, message in caplog.record_tuples]

    assert User.objects.all().count() == 7
    assert list(User.objects.order_by("email").values_list("email", "is_admin", "is_staff")) == [
        ("admin@teklia.com", True, True),
        ("contributor2@teklia.com", False, False),
        ("contributor3@teklia.com", False, False),
        ("contributor@teklia.com", False, False),
        ("manager@teklia.com", False, False),
        ("moderator@teklia.com", False, False),
        ("public@teklia.com", False, False),
    ]

    assert Project.objects.all().count() == 5
    for project in Project.objects.all():
        if "no users" in project.name:
            assert not Membership.objects.filter(project=project).exists()
        else:
            assert list(
                Membership.objects.filter(project=project).order_by("user__email").values_list("user__email", "role")
            ) == [
                ("contributor2@teklia.com", "Contributor"),
                ("contributor3@teklia.com", "Contributor"),
                ("contributor@teklia.com", "Contributor"),
                ("manager@teklia.com", "Manager"),
                ("moderator@teklia.com", "Moderator"),
            ]

    ml_classes = Class.objects.all()
    assert ml_classes.count() == 5
    assert [item.name for item in ml_classes] == ["Left margin", "Right margin", "Row", "Table footer", "Table header"]

    element_types = Type.objects.all()
    assert element_types.count() == 26
    assert set([item.name for item in element_types]) == set(
        ["folder", "page", "text_line", "paragraph", "text_zone", "word", "table", "row"]
    )

    assert list(
        Element.objects.values("type__name")
        .annotate(total=Count("type__name"))
        .order_by("total", "type__name")
        .values_list("type__name", "total")
    ) == [("table", 2), ("folder", 4), ("page", 30), ("row", 64), ("text_line", 526)]

    assert Campaign.objects.all().count() == 10
    assert list(
        Campaign.objects.all()
        .values("mode")
        .annotate(total=Count("mode"))
        .order_by("total", "mode")
        .values_list("mode", "total")
    ) == [
        ("classification", 1),
        ("element_group", 1),
        ("entity", 1),
        ("entity form", 1),
        ("transcription", 2),
        ("elements", 4),
    ]

    projects = Project.objects.all()
    for project in projects:
        if project.name != "Private project no users":
            assert Task.objects.filter(campaign__project=project).exists()
            if "with users" not in project.name:
                assert not TaskUser.objects.filter(task__campaign__project=project).exists()
            else:
                assert TaskUser.objects.filter(task__campaign__project=project).exists()
        else:
            assert not Task.objects.filter(campaign__project=project).exists()
