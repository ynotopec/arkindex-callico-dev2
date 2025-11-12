import uuid

import pytest
from django.conf import settings
from django.core import mail
from notifications.models import Notification
from notifications.signals import notify

from callico.annotations.models import Task, TaskUser
from callico.annotations.views import ANNOTATED_TASK_EDITED_VERB, PENDING_TASK_COMPLETED_VERB
from callico.projects.models import CampaignMode, Element, Role
from callico.users.models import User
from callico.users.tasks import send_daily_statistics, send_email

pytestmark = pytest.mark.django_db

DAILY_STATS_ADMIN = """
Hello,

This email contains a summary of the daily activity on the campaigns you manage.

Project "Managed project" - Campaign "Campaign"
  - User Contributor (contributor@callico.org) edited 3 already annotated task(s): https://callico.test/projects/campaign/%(managed)s/tasks/?user_id=%(contrib)s
  - User New contributor (new@callico.org) completed 3 pending task(s): https://callico.test/projects/campaign/%(managed)s/tasks/?user_id=%(new)s
  - User Super contributor (super@callico.org) completed 5 pending task(s) and edited 5 already annotated task(s): https://callico.test/projects/campaign/%(managed)s/tasks/?user_id=%(super)s

Project "Public project" - Campaign "Other campaign"
  - User New contributor (new@callico.org) completed 3 pending task(s): https://callico.test/projects/campaign/%(other)s/tasks/?user_id=%(new)s

See you tomorrow for another daily summary,

--
The Callico team
"""

DAILY_STATS_USER = """
Hello,

This email contains a summary of the daily activity on the campaigns you manage.

Project "Managed project" - Campaign "Campaign"
  - User Contributor (contributor@callico.org) edited 3 already annotated task(s): https://callico.test/projects/campaign/%(managed)s/tasks/?user_id=%(contrib)s
  - User New contributor (new@callico.org) completed 3 pending task(s): https://callico.test/projects/campaign/%(managed)s/tasks/?user_id=%(new)s
  - User Super contributor (super@callico.org) completed 5 pending task(s) and edited 5 already annotated task(s): https://callico.test/projects/campaign/%(managed)s/tasks/?user_id=%(super)s

Project "Public project" - Campaign "Other campaign"
  - User Contributor (contributor@callico.org) edited 3 already annotated task(s): https://callico.test/projects/campaign/%(other)s/tasks/?user_id=%(contrib)s

See you tomorrow for another daily summary,

--
The Callico team
"""


@pytest.mark.parametrize("with_html_message", [False, True])
def test_send_email(with_html_message):
    subject = "[IMPORTANT] Please read this email"
    message = "An important message"
    html_message = "<strong>" + message + "</strong>"
    recipients = ["bob@callico.org", "fred@callico.org"]

    # Directly calling the task (without going through Celery) to obtain synchronous results
    extra = {"html_message": html_message} if with_html_message else {}
    send_email(subject, message, recipients, **extra)

    assert len(mail.outbox) == 1

    sent_mail = mail.outbox[0]
    assert sent_mail.subject == subject
    assert sent_mail.body == message
    assert sent_mail.from_email == settings.DEFAULT_FROM_EMAIL
    assert sent_mail.to == recipients

    # If "html_message" is provided, we should send an HTML alternative of the email along with the plain text
    assert len(sent_mail.alternatives) == with_html_message
    if with_html_message:
        assert sent_mail.alternatives[0] == (html_message, "text/html")


def send_notification(user, managers, verb, campaign, times=1):
    user_tasks = list(TaskUser.objects.filter(task__in=campaign.tasks.all().order_by("created")))
    for i in range(0, times):
        notify.send(user, recipient=managers, verb=verb, action_object=user_tasks[i], target=campaign)


def test_send_daily_statistics(
    managed_campaign_with_tasks, new_contributor, contributor, public_project, arkindex_provider, image, admin, user
):
    # Generate activity for the managed campaign
    managed_campaign = managed_campaign_with_tasks
    inactive_contributor = User.objects.create(
        display_name="Inactive contributor", email="inactive@callico.org", password="inactive", is_admin=False
    )
    super_contributor = User.objects.create(
        display_name="Super contributor", email="super@callico.org", password="super", is_admin=False
    )
    for contrib in [inactive_contributor, super_contributor]:
        managed_campaign.project.memberships.create(user=contrib, role=Role.Contributor)

    # Lots of contributors
    users = User.objects.filter(memberships__project=managed_campaign.project)
    assert users.filter(memberships__role=Role.Contributor).count() == 4

    # A few managers
    managers = users.filter(memberships__role=Role.Manager)
    assert managers.count() == 2

    # Send lots of notifications
    # - inactive contributor didn't work today
    # - new contributor only completed pending tasks
    # - contributor only edited annotated tasks (but each task was edited twice)
    # - super contributor completed pending and edited annotated tasks
    send_notification(new_contributor, managers, PENDING_TASK_COMPLETED_VERB, managed_campaign, times=3)
    send_notification(contributor.user, managers, ANNOTATED_TASK_EDITED_VERB, managed_campaign, times=3)
    send_notification(contributor.user, managers, ANNOTATED_TASK_EDITED_VERB, managed_campaign, times=3)
    send_notification(super_contributor, managers, PENDING_TASK_COMPLETED_VERB, managed_campaign, times=5)
    send_notification(super_contributor, managers, ANNOTATED_TASK_EDITED_VERB, managed_campaign, times=5)
    assert Notification.objects.unsent().count() == 38

    # Generate activity for the other campaign
    other_campaign = public_project.campaigns.create(
        name="Other campaign",
        creator=admin.user,
        mode=CampaignMode.Transcription,
    )
    for manager in [admin.user, user.user]:
        public_project.memberships.create(user=manager, role=Role.Manager)
    for contrib in [new_contributor, contributor.user]:
        public_project.memberships.create(user=contrib, role=Role.Contributor)

    # A few contributors
    users = User.objects.filter(memberships__project=public_project).distinct()
    assert users.filter(memberships__role=Role.Contributor).count() == 2

    # A few managers
    assert users.filter(memberships__role=Role.Manager).count() == 2

    # Some user tasks
    page_type = public_project.types.create(name="Page")
    elements = Element.objects.bulk_create(
        [
            Element(
                name=f"Page {i}",
                type=page_type,
                project=public_project,
                provider=arkindex_provider,
                provider_object_id=uuid.uuid4(),
                image=image,
                order=i,
            )
            for i in range(1, 4)
        ]
    )
    TaskUser.objects.bulk_create(
        [
            TaskUser(user=contributor.user, task=Task.objects.create(element=element, campaign=other_campaign))
            for element in elements
        ],
        ignore_conflicts=True,
    )

    # Send a few notifications (but not to all managers)
    # - new contributor completed pending tasks
    # - contributor edited annotated tasks
    send_notification(new_contributor, admin.user, PENDING_TASK_COMPLETED_VERB, other_campaign, times=3)
    send_notification(contributor.user, user.user, ANNOTATED_TASK_EDITED_VERB, other_campaign, times=3)
    assert Notification.objects.unsent().count() == 44

    send_daily_statistics()

    # All notifications were alerted by email
    assert not Notification.objects.unsent().exists()
    assert Notification.objects.sent().count() == 44

    # The emails were properly sent to managers
    assert len(mail.outbox) == 2

    context_ids = {
        "managed": managed_campaign.id,
        "other": other_campaign.id,
        "new": new_contributor.id,
        "contrib": contributor.user.id,
        "super": super_contributor.id,
    }
    user_mail = mail.outbox[0]
    assert user_mail.subject == "Daily campaigns activity summary for managers - Callico"
    assert user_mail.body == DAILY_STATS_USER % context_ids
    assert user_mail.from_email == settings.DEFAULT_FROM_EMAIL
    assert user_mail.to == [user.user.email]

    admin_mail = mail.outbox[1]
    assert admin_mail.subject == "Daily campaigns activity summary for managers - Callico"
    assert admin_mail.body == DAILY_STATS_ADMIN % context_ids
    assert admin_mail.from_email == settings.DEFAULT_FROM_EMAIL
    assert admin_mail.to == [admin.user.email]
