import json
from datetime import timedelta
from urllib.parse import urljoin

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Count, F, Q
from django.http import HttpResponseRedirect
from django.http.response import Http404
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import translation
from django.utils.functional import cached_property
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy, pgettext_lazy
from django.views.generic import DetailView
from django.views.generic.edit import FormView
from notifications.signals import notify

from callico.annotations.forms import AnnotateForm, AnnotationParentForm, CommentCreateForm
from callico.annotations.models import Annotation, AnnotationState, Task, TaskState, TaskUser
from callico.projects.forms import (
    USER_TASK_ALL_FEEDBACKS,
    USER_TASK_AVAILABLE_STATE,
    USER_TASK_NO_FEEDBACK,
    USER_TASK_UNCERTAIN_FEEDBACK,
    USER_TASK_WITH_COMMENTS,
)
from callico.projects.mixins import ProjectACLMixin
from callico.projects.models import CampaignMode, CampaignState, Membership, Role, Type
from callico.users.models import Comment, User
from callico.users.tasks import send_email

PENDING_TASK_COMPLETED_VERB = "pending task completed"
ANNOTATED_TASK_EDITED_VERB = "annotated task edited"

NO_PARENT = "no-parent"


class ManagerRedirectionRequired(Exception):
    def __init__(
        self,
        element,
        message=_(
            "A manager is trying to access an annotation page, redirect them to the concerned element details page instead."
        ),
    ):
        self.element = element
        self.message = message
        super().__init__(self.message)


def get_interactive_image_context_parameters(task, element_children, help_text_str):
    params = {}
    context_ancestor = None
    context_type = task.campaign.configuration.get("context_type")
    if context_type:
        ancestors = task.element.all_ancestors()
        context_ancestor = ancestors.filter(type_id=context_type).last()

    interactive_element = task.element
    interactive_children = element_children
    if context_ancestor:
        type_name = Type.objects.get(id=context_type).name
        params["help_text"] = help_text_str % {"type": type_name}
        interactive_element = context_ancestor
        interactive_children = [task.element]

    params["element"] = json.dumps(interactive_element.serialize_frontend())
    params["children"] = json.dumps([child.serialize_frontend() for child in interactive_children])

    return params


def get_carousel_element_ids(task):
    carousel_type = task.campaign.configuration.get("carousel_type")
    return list(task.element.all_children().filter(type_id=carousel_type).values_list("id", flat=True))


def get_carousel_context_parameters(task, element_ids=None):
    params = {}

    # Let the carousel display the elements in InteractiveImage
    params["element"] = json.dumps(None)

    carousel_type = task.campaign.configuration.get("carousel_type")
    type_name = Type.objects.get(id=carousel_type).name if carousel_type else None
    params["carousel_type"] = type_name

    if element_ids is None:
        element_ids = get_carousel_element_ids(task)
    params["carousel_element_ids"] = json.dumps(element_ids, cls=DjangoJSONEncoder)

    params["display_carousel"] = True

    return params


class BaseTaskUserDetails(LoginRequiredMixin, ProjectACLMixin, DetailView):
    model = TaskUser
    context_object_name = "user_task"
    template_name = "user_task_details_base.html"

    def get_object(self):
        try:
            user_task = TaskUser.objects.select_related(
                "user", "task", "task__campaign", "task__campaign__project", "task__element__type"
            ).get(id=self.kwargs["pk"])
        except TaskUser.DoesNotExist:
            raise Http404(_("No user task matching this ID exists"))

        if not self.has_admin_access(user_task.task.campaign.project):
            raise PermissionDenied(_("You don't have access to this user task"))

        if user_task.task.campaign.state == CampaignState.Archived:
            raise PermissionDenied(
                _("You cannot view the details of a campaign marked as %(state)s")
                % {"state": user_task.task.campaign.get_state_display()}
            )

        return user_task

    def preprocess_answers(self):
        """
        Generic function to overwrite to retrieve information before formatting answers
        """
        pass

    def get_formatted_annotation(self, annotation):
        """
        Generic function to overwrite that must return the formatted answers
        """
        return {
            "version": annotation.version,
            "published": annotation.published,
            "state": {"value": annotation.state, "label": annotation.get_state_display()} if annotation.state else None,
            "moderator": annotation.moderator,
        }

    def get_children(self):
        """
        Generic function to overwrite that must return the children to display as polygons in InteractiveImage
        """
        return []

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        self.task = self.object.task

        self.children = self.get_children()
        interactive_image_params = get_interactive_image_context_parameters(
            self.task,
            self.children,
            _(
                'The annotated element is highlighted in green, currently displayed in the context of its first ancestor of type "%(type)s".'
            ),
        )
        context.update(interactive_image_params)

        # Display direct children of an element without image in a carousel
        if self.task.campaign.mode != CampaignMode.ElementGroup and not self.task.element.image_id:
            carousel_element_ids = list(self.task.element.children.all().values_list("id", flat=True))
            carousel_params = get_carousel_context_parameters(self.task, carousel_element_ids)
            context.update(carousel_params)

        context["display_image"] = True

        self.preprocess_answers()

        # Format annotations to display correct labels
        context["annotations"] = [
            self.get_formatted_annotation(annotation)
            for annotation in self.object.annotations.select_related("moderator").order_by("-version")
        ]

        context["extra_breadcrumb"] = {"title": _("Annotation"), "link_title": self.task.element}

        return context


class BaseTaskUserManage(LoginRequiredMixin, ProjectACLMixin, DetailView, FormView):
    model = TaskUser
    form_class = AnnotateForm
    context_object_name = "user_task"
    template_name = "user_task_manage_base.html"
    # Parent annotation
    parent = None
    # Children to display as polygons in InteractiveImage
    all_children = []

    def check_permissions(self, user_task):
        """
        Generic function to overwrite to add additional checks when retrieving the user task
        """
        if not user_task.task.campaign.project.memberships.filter(user=self.request.user).exists():
            raise PermissionDenied(_("You don't have access to this project"))

        if user_task.task.campaign.is_closed:
            raise PermissionDenied(
                _("You cannot %(action)s a task for a campaign marked as %(state)s")
                % {
                    "action": self.action.lower(),
                    "state": user_task.task.campaign.get_state_display(),
                }
            )

    def get_parent(self, user_task):
        """
        Generic function to overwrite to retrieve the parent annotation
        """
        # By default the parent is the last annotation
        return user_task.annotations.order_by("-version").first()

    def get_object_from_task(self):
        """
        Checks if the ID in the URL is that of a task.
        Maintains backward compatibility with versions ⩽ 0.5.0-post1
        """
        try:
            task = Task.objects.select_related("element__type", "campaign__project").get(id=self.kwargs["pk"])
        except Task.DoesNotExist:
            return

        # Return zero or one user task due to DB constraint
        user_task = task.user_tasks.filter(user=self.request.user).first()

        if not user_task and self.has_admin_access(task.campaign.project):
            raise ManagerRedirectionRequired(task.element)

        return user_task

    def get_object(self):
        try:
            user_task = TaskUser.objects.select_related("task__element__type", "task__campaign__project").get(
                id=self.kwargs["pk"]
            )
        except TaskUser.DoesNotExist:
            user_task = self.get_object_from_task()
            if not user_task:
                raise Http404(_("No user task matching this ID exists"))

        self.can_admin = self.has_admin_access(user_task.task.campaign.project)

        self.check_permissions(user_task)

        self.initial_state = user_task.state
        self.parent = self.get_parent(user_task)

        return user_task

    def get_value(self, form):
        """
        Generic function to overwrite that must return the value of the annotation
        """
        return {}

    def get_manage_url(self, user_task):
        """
        Generic function to overwrite to retrieve the URL of a user task
        """
        return None

    @property
    def completion_time(self):
        time_ms = self.request.POST.get("completion_time")
        try:
            time_ms = int(time_ms)
        except (TypeError, ValueError):
            return None
        return timedelta(milliseconds=time_ms)

    @property
    def query_params(self):
        query_params = "&".join(
            [
                f"{key}={value}"
                for key, value in self.request.GET.items()
                if key in ["state", "user_id", "user_feedback"]
            ]
        )
        return f"?{query_params}" if query_params else ""

    @property
    def queryset_filters(self):
        filters = Q()

        state = self.request.GET.get("state")
        if state:
            filters &= Q(state=state)

        user_feedback = self.request.GET.get("user_feedback")
        if user_feedback in [USER_TASK_UNCERTAIN_FEEDBACK, USER_TASK_ALL_FEEDBACKS]:
            filters &= Q(has_uncertain_value=True)
        if user_feedback in [USER_TASK_WITH_COMMENTS, USER_TASK_ALL_FEEDBACKS]:
            filters &= Q(task__comments__isnull=False)
        if user_feedback == USER_TASK_NO_FEEDBACK:
            filters &= Q(has_uncertain_value=False) & Q(task__comments__isnull=True)

        user_id = self.request.GET.get("user_id")
        if user_id and user_id.isdigit():
            filters &= Q(user_id=user_id)

        return filters

    @property
    def filter_text(self):
        filter_text_translations = {
            TaskState.Draft: pgettext_lazy("plural", "draft"),
            TaskState.Pending: pgettext_lazy("plural", "pending"),
            TaskState.Annotated: pgettext_lazy("plural", "annotated"),
            TaskState.Validated: pgettext_lazy("plural", "validated"),
            TaskState.Rejected: pgettext_lazy("plural", "rejected"),
            TaskState.Skipped: pgettext_lazy("plural", "skipped"),
        }

        # Always display the state
        state_parameter = self.request.GET.get("state")

        return _("You are browsing all %(article)s tasks") % {"article": self.plural_article} + (
            # Translators: This translation concerns the text of the task filter. It is followed by a status
            # of the task (pending, annotated...) and therefore does not need to be translated into French.
            _(" which are ") + filter_text_translations.get(state_parameter, state_parameter) if state_parameter else ""
        )

    @cached_property
    def all_user_tasks(self):
        return (
            TaskUser.objects.select_related("task", "task__campaign")
            .filter(task__campaign_id=self.object.task.campaign_id)
            # The order is the same as when listing tasks
            # Without this order, the list would not be consistent with the task list
            .order_by("task__created", "task_id", "created", "id")
        )

    @cached_property
    def filtered_user_tasks_list(self):
        return (
            # The state of the current user task can be different of the filter
            self.all_user_tasks.filter(Q(id=self.object.id) | self.queryset_filters).distinct()
            if self.queryset_filters
            else self.all_user_tasks
        )

    @cached_property
    def previous_user_task_url(self):
        previous_user_task = self.filtered_user_tasks_list.filter(task__created__lt=self.object.task.created).last()
        if previous_user_task is None:
            return None
        return self.get_manage_url(previous_user_task) + self.query_params

    @cached_property
    def next_user_task_url(self):
        next_user_task = self.filtered_user_tasks_list.filter(task__created__gt=self.object.task.created).first()
        if next_user_task is None:
            return None
        return self.get_manage_url(next_user_task) + self.query_params

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["instance"] = self.object.task
        return kwargs

    def form_valid(self, form):
        # If next_user_task_url is empty, we have reached the end of the navigation and should go back to the task list
        if self.next_user_task_url:
            messages.add_message(
                self.request,
                messages.SUCCESS,
                _(
                    "Task has been %(action)s, you have been redirected to %(article)s next task for the campaign %(campaign)s"
                )
                % {
                    "action": self.object.get_state_display().lower(),
                    "article": self.single_article,
                    "campaign": self.object.task.campaign,
                },
                extra_tags="hide-after-delay",
            )
            return super().form_valid(form)

        # If the user was on a task that was never annotated/moderated before and there are no more tasks to be
        # annotated/moderated then this means that they have finished processing all their tasks and we display a message
        self.unmanaged_tasks_exist = self.all_user_tasks.filter(state__in=self.unmanaged_task_states).exists()
        if self.initial_state in self.unmanaged_task_states and not self.unmanaged_tasks_exist:
            messages.add_message(
                self.request,
                messages.SUCCESS,
                _("You have processed all %(article)s tasks for the campaign %(campaign)s")
                % {
                    "article": self.plural_article,
                    "campaign": self.object.task.campaign,
                },
            )

        return super().form_valid(form)

    def get_success_url(self):
        # If next_user_task_url is empty, we have reached the end of the navigation and should go back to the task list
        if self.next_user_task_url:
            return self.next_user_task_url

        # If there are still tasks matching the filters then we redirect to the filtered list, otherwise we redirect to the full list
        query_params = self.query_params if self.all_user_tasks.filter(self.queryset_filters).exists() else ""
        if self.can_admin:
            return reverse("admin-campaign-task-list", kwargs={"pk": self.object.task.campaign.id}) + query_params

        # If the user was annotating a task from the filtered list and there are no more tasks to annotate,
        # then we redirect to the list of available tasks
        if (
            self.request.GET.get("state") in self.unmanaged_task_states
            and not self.unmanaged_tasks_exist
            and (
                self.object.task.campaign.tasks.annotate(
                    nb_user_tasks=Count("user_tasks", filter=Q(user_tasks__is_preview=False))
                )
                .filter(nb_user_tasks__lt=F("campaign__max_user_tasks"))
                .exclude(user_tasks__user=self.user)
                .exists()
            )
        ):
            query_params = f"?state={USER_TASK_AVAILABLE_STATE}"

        return reverse("contributor-campaign-task-list", kwargs={"pk": self.object.task.campaign.id}) + query_params

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # To enable fluidity on the base container
        context["fluid_container"] = True

        context["can_admin"] = self.can_admin
        context["parent_id"] = self.parent.id if self.parent else NO_PARENT

        interactive_image_params = get_interactive_image_context_parameters(
            self.object.task,
            self.all_children,
            _(
                'The element to annotate is highlighted in green, currently displayed in the context of its first ancestor of type "%(type)s".'
            ),
        )
        context.update(interactive_image_params)

        # Display direct children of an element without image in a carousel
        if self.object.task.campaign.mode != CampaignMode.ElementGroup and not self.object.task.element.image_id:
            carousel_element_ids = list(self.object.task.element.children.all().values_list("id", flat=True))
            carousel_params = get_carousel_context_parameters(self.object.task, carousel_element_ids)
            context.update(carousel_params)

        context["display_image"] = True

        # Get previous/next annotations
        context["previous"] = self.previous_user_task_url
        context["next"] = self.next_user_task_url
        context["filter_text"] = self.filter_text

        # Breadcrumb parameters
        context["add_pending_filter"] = self.initial_state == TaskState.Pending
        context["extra_breadcrumb"] = {
            "title": self.extra_breadcrumb_title,
            "link_title": self.object.task.element,
        }

        return context

    def get(self, request, *args, **kwargs):
        try:
            self.object = self.get_object()
        except ManagerRedirectionRequired as e:
            element = e.element
            url, kwargs = (
                ("element-details", {"pk": element.id})
                if not element.type.folder
                else ("project-browse", {"project_id": element.project_id, "element_id": element.id})
            )
            return HttpResponseRedirect(reverse(url, kwargs=kwargs))

        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)

    def post_parameter_is_valid(self):
        """
        Generic function to overwrite to check if the parameters of the POST request are valid
        """
        return True

    def post(self, request, *args, **kwargs):
        try:
            self.object = self.get_object()
        except ManagerRedirectionRequired as e:
            element = e.element
            url, kwargs = (
                ("element-details", {"pk": element.id})
                if not element.type.folder
                else ("project-browse", {"project_id": element.project_id, "element_id": element.id})
            )
            return HttpResponseRedirect(reverse(url, kwargs=kwargs))

        form = self.get_form()

        if self.post_parameter_is_valid() or form.is_valid():
            return self.form_valid(form)

        return self.form_invalid(form)


class BaseTaskUserAnnotate(BaseTaskUserManage):
    unmanaged_task_states = [TaskState.Pending]

    action = gettext_lazy("Annotate")
    single_article = gettext_lazy("your")
    plural_article = pgettext_lazy("plural", "your")
    extra_breadcrumb_title = gettext_lazy("Annotation")

    def check_permissions(self, user_task):
        super().check_permissions(user_task)

        if user_task.user != self.request.user:
            if self.can_admin:
                raise ManagerRedirectionRequired(user_task.task.element)

            raise PermissionDenied(_("You are not assigned to this task"))

        if user_task.state in [TaskState.Draft, TaskState.Validated]:
            raise Http404(
                _("You cannot annotate a task marked as %(state)s") % {"state": user_task.get_state_display()}
            )

    def get_parent(self, user_task):
        # Update parent annotation from the GET parameter
        if "parent_id" in self.request.GET:
            try:
                return user_task.annotations.get(id=self.request.GET["parent_id"])
            except Annotation.DoesNotExist:
                pass

        return super().get_parent(user_task)

    def get_manage_url(self, user_task):
        return user_task.annotate_url

    @property
    def filter_text(self):
        state_parameter = self.request.GET.get("state")
        user_feedback_parameter = self.request.GET.get("user_feedback")

        filter_text = super().filter_text

        if user_feedback_parameter:
            filter_text_translations = {
                USER_TASK_NO_FEEDBACK: pgettext_lazy("plural", "without comments and not uncertain"),
                USER_TASK_WITH_COMMENTS: _("with comments"),
                USER_TASK_UNCERTAIN_FEEDBACK: pgettext_lazy("plural", "uncertain"),
                USER_TASK_ALL_FEEDBACKS: pgettext_lazy("plural", "with comments and uncertain"),
            }
            separator = (
                _(", ") if user_feedback_parameter in [USER_TASK_NO_FEEDBACK, USER_TASK_ALL_FEEDBACKS] else _(" and ")
            )
            # Translators: This translation concerns the text of the task filter. It is followed by a status
            # of the task (pending, annotated...) and therefore does not need to be translated into French.
            filter_text += (separator if state_parameter else _(" which are ")) + filter_text_translations.get(
                user_feedback_parameter, user_feedback_parameter
            )

        return filter_text

    @cached_property
    def all_user_tasks(self):
        return (
            super()
            .all_user_tasks.exclude(state__in=[TaskState.Draft, TaskState.Validated])
            .filter(user=self.request.user)
        )

    def form_valid(self, form):
        if "skip" in self.request.POST:
            self.object.state = TaskState.Skipped
            self.object.save()
            return super().form_valid(form)

        value = self.get_value(form)
        self.object.annotations.create(
            parent=self.parent,
            value=value,
            duration=self.completion_time,
        )

        self.object.state = TaskState.Annotated
        self.object.save()

        # Store notifications about the user activity for the daily statistics email
        notification_verb = (
            PENDING_TASK_COMPLETED_VERB if self.initial_state == TaskState.Pending else ANNOTATED_TASK_EDITED_VERB
        )
        project_managers = User.objects.filter(
            memberships__project=self.object.task.campaign.project, memberships__role=Role.Manager
        )
        notify.send(
            self.request.user,
            recipient=project_managers,
            verb=notification_verb,
            action_object=self.object,
            target=self.object.task.campaign,
        )

        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["parent_form"] = AnnotationParentForm(self.object, self.parent)
        return context

    def post_parameter_is_valid(self):
        return "skip" in self.request.POST


class BaseTaskUserModerate(BaseTaskUserManage):
    unmanaged_task_states = [TaskState.Skipped, TaskState.Pending, TaskState.Annotated]

    action = gettext_lazy("Moderate")
    single_article = pgettext_lazy("feminine", "the")
    plural_article = pgettext_lazy("plural", "the")
    extra_breadcrumb_title = gettext_lazy("Moderation")

    def check_permissions(self, user_task):
        super().check_permissions(user_task)

        if not self.can_admin:
            raise PermissionDenied(_("You don't have the required rights on this project to moderate tasks"))

        if user_task.state == TaskState.Draft:
            raise ManagerRedirectionRequired(user_task.task.element)

    def get_manage_url(self, user_task):
        return user_task.moderate_url

    @property
    def filter_text(self):
        state_parameter = self.request.GET.get("state")
        user_feedback_parameter = self.request.GET.get("user_feedback")
        user_id_parameter = self.request.GET.get("user_id")
        user_parameter = (
            User.objects.filter(id=user_id_parameter).first()
            if user_id_parameter and user_id_parameter.isdigit()
            else None
        )

        filter_text = super().filter_text

        if user_feedback_parameter:
            filter_text_translations = {
                USER_TASK_NO_FEEDBACK: pgettext_lazy("plural", "without comments, not uncertain")
                if user_parameter
                else pgettext_lazy("plural", "without comments and not uncertain"),
                USER_TASK_WITH_COMMENTS: _("with comments"),
                USER_TASK_UNCERTAIN_FEEDBACK: pgettext_lazy("plural", "uncertain"),
                USER_TASK_ALL_FEEDBACKS: pgettext_lazy("plural", "with comments, uncertain")
                if user_parameter
                else pgettext_lazy("plural", "with comments and uncertain"),
            }
            separator = (
                _(", ")
                if user_parameter or user_feedback_parameter in [USER_TASK_NO_FEEDBACK, USER_TASK_ALL_FEEDBACKS]
                else _(" and ")
            )
            # Translators: This translation concerns the text of the task filter. It is followed by a status
            # of the task (pending, annotated...) and therefore does not need to be translated into French.
            filter_text += (separator if state_parameter else _(" which are ")) + filter_text_translations.get(
                user_feedback_parameter, user_feedback_parameter
            )

        if user_parameter:
            filter_text += (_(" and") if state_parameter or user_feedback_parameter else "") + pgettext_lazy(
                "plural", " assigned to %(user)s"
            ) % {"user": user_parameter}

        return filter_text

    @cached_property
    def all_user_tasks(self):
        return super().all_user_tasks.exclude(state=TaskState.Draft)

    def form_valid(self, form):
        if "reject" in self.request.POST:
            # self.parent can be null if the user task was pending or skipped
            if self.parent:
                self.parent.state = AnnotationState.Rejected
                self.parent.moderator = self.request.user
                self.parent.save()

            self.object.state = TaskState.Rejected
            self.object.save()

            return super().form_valid(form)

        value = self.get_value(form)
        annotation = (
            self.object.annotations.create(
                parent=self.parent,
                value=value,
                duration=self.completion_time,
            )
            # We create a new annotation if the value was corrected
            if not self.parent or value != self.parent.value
            else self.parent
        )

        if annotation == self.parent:
            annotation.state = AnnotationState.Validated
        annotation.moderator = self.request.user
        annotation.save()

        self.object.state = TaskState.Validated
        self.object.save()

        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["parent"] = self.parent
        context["moderate"] = True
        return context

    def post_parameter_is_valid(self):
        return "reject" in self.request.POST


class TaskDiscussion(LoginRequiredMixin, ProjectACLMixin, FormView):
    form_class = CommentCreateForm
    template_name = "task_discussion.html"
    user_task = None

    def get_object(self):
        try:
            task = (
                Task.objects.select_related(
                    "element",
                    "element__type",
                    "element__image",
                    "campaign",
                    "campaign__project",
                )
                .prefetch_related("comments", "comments__user")
                .get(id=self.kwargs["pk"])
            )
        except Task.DoesNotExist:
            raise Http404(_("No task matching this ID exists"))

        # Check if the user is a contributor assigned to the task or a project moderator/manager
        error_403 = PermissionDenied(_("You don't have the required rights to comment on this task"))
        try:
            membership = task.campaign.project.memberships.get(user=self.request.user)
        except Membership.DoesNotExist:
            raise error_403

        if membership.role == Role.Contributor:
            try:
                self.user_task = task.user_tasks.get(user=self.request.user)
            except TaskUser.DoesNotExist:
                raise error_403

        if task.campaign.is_closed:
            raise PermissionDenied(
                _("You cannot %(action)s a task for a campaign marked as %(state)s")
                % {
                    "action": pgettext_lazy("verb", "Comment").lower(),
                    "state": task.campaign.get_state_display(),
                }
            )

        return task

    @property
    def query_params(self):
        query_params = "&".join(
            [
                f"{key}={value}"
                for key, value in self.request.GET.items()
                if key in ["from", "state", "user_id", "user_feedback"]
            ]
        )
        return f"?{query_params}" if query_params else ""

    def get_form_kwargs(self):
        # Retrieving the task now to raise errors if the user shouldn't access this page
        self.object = self.get_object()

        # Retrieving managers/moderators now to avoid duplicating queries between context and form submit
        self.managers = User.objects.filter(
            memberships__project=self.object.campaign.project, memberships__role=Role.Manager
        )
        self.moderators = User.objects.filter(
            memberships__project=self.object.campaign.project, memberships__role=Role.Moderator
        )

        return super().get_form_kwargs()

    def form_valid(self, form):
        comment = Comment.objects.create(
            user=self.request.user,
            task=self.object,
            content=form.cleaned_data["content"],
        )

        context = {
            "user": str(self.request.user),
            "campaign_name": self.object.campaign.name,
            "project_name": self.object.campaign.project.name,
            "comment": comment.content,
            "task_discussion": urljoin(
                settings.INSTANCE_URL, reverse("task-discussion", kwargs={"pk": self.object.id})
            ),
        }

        # Send an email to all the participants to notify that a user commented on the discussion
        participants_ids = self.object.comments.values_list("user", flat=True).distinct()
        recipients = list(User.objects.filter(id__in=participants_ids))
        can_moderate = list(self.managers) + list(self.moderators)
        msg = _("Your comment was well taken into account and an email was sent to the participants in this discussion")

        # If a contributor commented, also notify managers
        if self.user_task:
            recipients += list(self.managers)
            msg += _(
                " and to the managers of this campaign. Please, go back to the previous tab to pursue your annotation"
            )

        for recipient in set(recipients):
            if recipient == self.request.user:
                continue

            context["task_moderation"] = None
            if self.user_task and recipient in can_moderate:
                context["task_moderation"] = urljoin(settings.INSTANCE_URL, self.user_task.moderate_url)

            context["task_annotation"] = None
            if recipient not in can_moderate:
                context["task_annotation"] = urljoin(settings.INSTANCE_URL, self.object.annotate_url)

            with translation.override(recipient.preferred_language):
                message = render_to_string("mails/update_on_followed_discussion.html", context=context)
                send_email.delay(
                    _("A user commented on a task discussion from %(campaign)s - Callico")
                    % {"campaign": self.object.campaign},
                    message,
                    [recipient.email],
                )

        messages.add_message(self.request, messages.INFO, msg + ".")

        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["task"] = self.object
        context["managers"] = self.managers
        context["moderators"] = self.moderators

        # Display a carousel for the "ElementGroup" campaigns
        if self.object.campaign.mode == CampaignMode.ElementGroup:
            carousel_params = get_carousel_context_parameters(self.object)
            context.update(carousel_params)

        # Breadcrumb parameters
        context["can_admin"] = self.has_admin_access(self.object.campaign.project)
        context["add_pending_filter"] = self.user_task.state == TaskState.Pending if self.user_task else False
        context["extra_breadcrumb"] = {"title": _("Discussion"), "link_title": self.object.element}

        return context

    def get_success_url(self):
        return reverse("task-discussion", kwargs={"pk": self.object.id}) + self.query_params
