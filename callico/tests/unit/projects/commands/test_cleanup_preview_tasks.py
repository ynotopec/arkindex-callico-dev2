import logging

import pytest
from django.core.management import call_command

from callico.annotations.models import Task, TaskState, TaskUser

pytestmark = pytest.mark.django_db


def test_cleanup_preview_tasks(caplog, managed_campaign, admin, user):
    elements = managed_campaign.project.elements.filter(image__isnull=False)
    count = elements.count()
    tasks = Task.objects.bulk_create([Task(element=element, campaign=managed_campaign) for element in elements])
    users_loop = [admin.user] * count + [user.user] * count
    tasks_loop = tasks * 2
    TaskUser.objects.bulk_create(
        [
            TaskUser(task=task, user=user, state=TaskState.Pending, is_preview=True)
            for user, task in zip(users_loop, tasks_loop)
        ]
    )

    assert TaskUser.objects.filter(is_preview=True)

    call_command(
        "cleanup_preview_tasks",
    )

    assert not TaskUser.objects.filter(is_preview=True)
    assert [(level, message) for _module, level, message in caplog.record_tuples] == [
        (logging.INFO, f"Retrieved {count * 2} preview user tasks to be deleted."),
        (logging.INFO, "Deleted all preview user tasks."),
    ]
