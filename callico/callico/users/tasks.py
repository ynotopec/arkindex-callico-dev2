from urllib.parse import urljoin

from celery import shared_task
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.aggregates.general import ArrayAgg
from django.core.mail import send_mail
from django.db.models import Q
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import translation
from django.utils.translation import gettext as _
from notifications.models import Notification

from callico.annotations.models import TaskUser
from callico.projects.models import Campaign, Role
from callico.users.models import User


@shared_task
def send_email(subject, message, recipients, html_message=None):
    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=recipients,
        fail_silently=False,
        html_message=html_message,
    )


@shared_task
def send_daily_statistics():
    from callico.annotations.views import ANNOTATED_TASK_EDITED_VERB, PENDING_TASK_COMPLETED_VERB

    user_content_type = ContentType.objects.get_for_model(User)
    task_user_content_type = ContentType.objects.get_for_model(TaskUser)
    campaign_content_type = ContentType.objects.get_for_model(Campaign)

    managers = User.objects.filter(memberships__role=Role.Manager).distinct()
    for manager in managers:
        with translation.override(manager.preferred_language):
            global_summary = []
            for campaign in Campaign.objects.filter(
                project__memberships__user=manager, project__memberships__role=Role.Manager
            ).order_by("project__name", "name"):
                unsent_notifications = Notification.objects.unsent().filter(
                    recipient=manager,
                    verb__in=[PENDING_TASK_COMPLETED_VERB, ANNOTATED_TASK_EDITED_VERB],
                    actor_content_type=user_content_type,
                    action_object_content_type=task_user_content_type,
                    target_content_type=campaign_content_type,
                    target_object_id=campaign.id,
                )

                campaign_stats = unsent_notifications.values("actor_object_id").annotate(
                    pending_ids=ArrayAgg("action_object_object_id", filter=Q(verb=PENDING_TASK_COMPLETED_VERB)),
                    edited_ids=ArrayAgg("action_object_object_id", filter=Q(verb=ANNOTATED_TASK_EDITED_VERB)),
                )
                # If no activity was detected on the campaign, no need to alert the manager
                if not campaign_stats:
                    continue

                campaign_tasks_url = reverse("admin-campaign-task-list", kwargs={"pk": campaign.id})
                campaign_summary = [
                    _('Project "%(project)s" - Campaign "%(campaign)s"')
                    % {
                        "project": campaign.project,
                        "campaign": campaign.name,
                    }
                ]

                project_users = {
                    str(user.id): (user.display_name, user.email)
                    for user in User.objects.filter(memberships__project_id=campaign.project_id)
                }
                for user_stats in campaign_stats:
                    user_id = user_stats["actor_object_id"]

                    user_activity = []
                    if user_stats["pending_ids"]:
                        user_activity.append(
                            _("completed %(pending)s pending task(s)") % {"pending": len(user_stats["pending_ids"])}
                        )
                    if user_stats["edited_ids"]:
                        # If a task was edited multiple times by the same user, we only want to alert one edition
                        reduced_edited_ids = set(user_stats["edited_ids"])
                        user_activity.append(
                            _("edited %(edited)s already annotated task(s)") % {"edited": len(reduced_edited_ids)}
                        )

                    user_tasks_url = urljoin(settings.INSTANCE_URL, f"{campaign_tasks_url}?user_id={user_id}")

                    campaign_summary.append(
                        _("  - User %(display_name)s (%(email)s) %(activity)s: %(url)s")
                        % {
                            "display_name": project_users[user_id][0],
                            "email": project_users[user_id][1],
                            "activity": _(" and ").join(user_activity),
                            "url": user_tasks_url,
                        }
                    )

                global_summary.append("\n".join(campaign_summary))

                # Mark all notifications, which will be in the summary, as sent, to avoid listing them in the next daily email
                unsent_notifications.mark_as_sent()

            # If no activity was detected at all, no need to send an empty email to the manager
            if not global_summary:
                continue

            message = render_to_string(
                "mails/daily_statistics.html",
                context={"content": "\n\n".join(global_summary)},
            )
            send_email(
                _("Daily campaigns activity summary for managers - Callico"),
                message,
                [manager.email],
            )
