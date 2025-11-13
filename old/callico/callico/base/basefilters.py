import json
import logging

from django import template
from django.contrib.messages import ERROR, INFO, SUCCESS, WARNING
from django.utils.safestring import mark_safe
from django.utils.translation import ngettext

from callico.annotations.models import AnnotationState, TaskState
from callico.process.models import ProcessState
from callico.projects.models import CampaignState, Role
from callico.projects.views import ProgressBarExtraTaskState

register = template.Library()


@register.filter
def message_class(message):
    classes = {
        INFO: "is-info",
        SUCCESS: "is-success",
        WARNING: "is-warning",
        ERROR: "is-danger",
    }
    return classes.get(message.level, "")


@register.filter
def role_class(role):
    classes = {
        Role.Contributor: "",
        Role.Moderator: "is-info",
        Role.Manager: "is-success",
    }
    return classes.get(role, "")


@register.filter
def process_class(process):
    classes = {
        ProcessState.Created: "is-info",
        ProcessState.Running: "is-warning",
        ProcessState.Completed: "is-success",
        ProcessState.Error: "is-danger",
    }
    return classes.get(process.state, "")


@register.filter
def log_class(log):
    classes = {
        logging.DEBUG: "has-text-grey",
        logging.INFO: "",
        logging.WARNING: "has-text-warning-darker",
        logging.ERROR: "has-text-danger",
    }
    return classes.get(log["level"], "")


@register.filter
def log_tag_class(log_level):
    classes = {
        logging.DEBUG: "",
        logging.INFO: "",
        logging.WARNING: "is-warning-darker",
        logging.ERROR: "is-danger",
    }
    return classes.get(log_level, "")


@register.filter
def campaign_class(campaign):
    classes = {
        CampaignState.Created: "is-warning",
        CampaignState.Running: "is-success",
        CampaignState.Closed: "is-danger",
        CampaignState.Archived: "",
    }
    return classes.get(campaign.state, "")


@register.filter
def task_class(task_state):
    classes = {
        TaskState.Draft: "",
        ProgressBarExtraTaskState.Uncertain: "is-warning",
        TaskState.Pending: "is-warning",
        TaskState.Annotated: "is-info",
        TaskState.Validated: "is-success",
        TaskState.Rejected: "is-danger",
        TaskState.Skipped: "",
    }
    return classes.get(task_state, "")


@register.filter
def annotation_class(annotation_state):
    classes = {
        AnnotationState.Validated: "is-success",
        AnnotationState.Rejected: "is-danger",
    }
    return classes.get(annotation_state, "")


@register.filter
def progress_bar_colors(state):
    classes = {
        TaskState.Pending: "has-background-warning",
        TaskState.Annotated: "has-background-info",
        TaskState.Validated: "has-background-success",
        TaskState.Rejected: "has-background-danger",
        TaskState.Skipped: "has-background-dark",
    }
    return classes.get(state, "")


@register.filter
def humanize_timedelta(time_delta):
    """Display a timedelta in minutes and seconds"""
    seconds = time_delta.seconds % 60
    minutes = int(time_delta.seconds / 60)

    message = ngettext("%d second", "%d seconds", seconds) % seconds
    if minutes >= 1:
        message = " ".join(
            (
                ngettext("%d minute", "%d minutes", minutes) % minutes,
                message,
            )
        )
    return message


@register.filter
def jsonify(variable, is_safe=True):
    if is_safe:
        return mark_safe(json.dumps(variable))
    return json.dumps(variable)


@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)
