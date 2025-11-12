import math
from itertools import groupby
from operator import itemgetter
from urllib.parse import urljoin

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import BadRequest, PermissionDenied
from django.db import models, transaction
from django.db.models import (
    Case,
    Count,
    DurationField,
    Exists,
    F,
    IntegerField,
    Max,
    OuterRef,
    Prefetch,
    Q,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Coalesce, Greatest, Lower
from django.forms import Form, formset_factory
from django.http.response import Http404, HttpResponseRedirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import translation
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy, pgettext_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView, View
from django.views.generic.detail import SingleObjectMixin
from django.views.generic.edit import BaseDeleteView, FormMixin, FormView

from callico.annotations.models import USER_TASK_COMPLETED_STATES, Annotation, Task, TaskState, TaskUser
from callico.base.db import Median
from callico.process.arkindex.exports import ARKINDEX_PUBLISH_METHODS
from callico.projects.forms import (
    ALGORITHM_RANDOM,
    ALGORITHM_SEQUENTIAL,
    ELEMENT_SELECTION_UNUSED,
    NO_USER,
    REQUIRED_CSS_CLASS,
    USER_TASK_ALL_FEEDBACKS,
    USER_TASK_AVAILABLE_STATE,
    USER_TASK_NO_FEEDBACK,
    USER_TASK_UNCERTAIN_FEEDBACK,
    USER_TASK_WITH_COMMENTS,
    AdminCampaignTasksListForm,
    BaseCampaignUpdateForm,
    CampaignCreateForm,
    CampaignTasksCreateForm,
    ClassificationCampaignUpdateForm,
    ContextualizedCampaignUpdateForm,
    ContributorCampaignTasksListForm,
    ElementGroupCampaignUpdateForm,
    ElementsCampaignUpdateForm,
    EntityCampaignUpdateForm,
    EntityCampaignUpdateFormset,
    EntityFormCampaignUpdateForm,
    EntityFormFieldForm,
    EntityFormGroupForm,
    MembershipForm,
    ProjectManagementForm,
    TranscriptionCampaignUpdateForm,
)
from callico.projects.mixins import ProjectACLMixin
from callico.projects.models import (
    CSV_SUPPORTED_CAMPAIGN_MODES,
    XLSX_SUPPORTED_CAMPAIGN_MODES,
    Authority,
    Campaign,
    CampaignMode,
    CampaignState,
    Element,
    Image,
    Membership,
    Project,
    ProviderType,
    Role,
    generate_token,
)
from callico.projects.utils import ENTITY_FORM_GROUP_MODE, find_configured_sorted_field, find_configured_sorted_group
from callico.users.models import User
from callico.users.tasks import send_email


class ProgressBarExtraTaskState(models.TextChoices):
    Available = USER_TASK_AVAILABLE_STATE, gettext_lazy("Available")
    Uncertain = USER_TASK_UNCERTAIN_FEEDBACK, pgettext_lazy("feminine", "Uncertain")


PROGRESS_BAR_ORDER = [
    TaskState.Validated,
    TaskState.Annotated,
    TaskState.Skipped,
    TaskState.Rejected,
    ProgressBarExtraTaskState.Uncertain,
    TaskState.Pending,
    ProgressBarExtraTaskState.Available,
]


CAMPAIGN_UPDATE_FORMS = {
    CampaignMode.Transcription: TranscriptionCampaignUpdateForm,
    CampaignMode.Classification: ClassificationCampaignUpdateForm,
    CampaignMode.Entity: EntityCampaignUpdateForm,
    CampaignMode.EntityForm: EntityFormCampaignUpdateForm,
    CampaignMode.ElementGroup: ElementGroupCampaignUpdateForm,
    CampaignMode.Elements: ElementsCampaignUpdateForm,
}


def get_user_task_state_counts(queryset):
    counts = queryset.aggregate(
        total=Count("user_tasks__pk", filter=~Q(user_tasks__state=TaskState.Draft)),
        completed=Count("user_tasks__pk", filter=Q(user_tasks__state__in=USER_TASK_COMPLETED_STATES)),
        **{state: Count("user_tasks__pk", filter=Q(user_tasks__state=state)) for state in TaskState},
    )

    # We need to add the Sum aggregation after the Count ones because there are conflicts between:
    # - the available_assignments annotation,
    # - the Count aggregations,
    # - and the Sum aggregation,
    # resulting from extra JOIN and GROUP BY clauses, having the Sum aggregation directly next to the
    # others would output erroneous values when there are multiple TaskUser objects linked to a Task.
    counts.update(
        queryset.aggregate(
            **{
                ProgressBarExtraTaskState.Available: Coalesce(
                    Sum("available_assignments", filter=Q(available_assignments__gte=0)), Value(0)
                )
            }
        )
    )

    return counts


class FormFilteredListView(FormMixin, ListView):
    form = None

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.request.method == "GET":
            kwargs["data"] = self.request.GET
        return kwargs

    def get_form(self, *args, **kwargs):
        # Cache form to avoid querying multiple times
        if self.form is None:
            self.form = super().get_form(*args, **kwargs)
        return self.form

    def get_queryset(self):
        qs = super().get_queryset()
        self.get_form()
        if not self.form.is_valid():
            return qs
        return self.filter_queryset(qs, **self.form.cleaned_data)

    def filter_queryset(self, qs, **filters):
        # Ignore empty values by default
        return qs.filter(**{k: v for k, v in filters.items() if v or v is False})


class ProjectList(ProjectACLMixin, ListView):
    model = Project
    paginate_by = 18
    template_name = "project_list.html"
    context_object_name = "projects"

    def get_queryset(self):
        if self.user.is_anonymous:
            return Project.objects.filter(public=True).order_by("name")

        qs = self.readable_projects.order_by("name")
        if "public" in self.request.GET and self.request.GET["public"]:
            return qs.exclude(memberships__user=self.user)

        return qs.filter(memberships__user=self.user)


class ProjectBrowse(LoginRequiredMixin, ProjectACLMixin, ListView):
    model = Element
    paginate_by = 20
    template_name = "project_browse.html"
    context_object_name = "elements"

    def get_project(self):
        project = super().get_project()
        if not self.has_admin_access(project):
            raise PermissionDenied(_("You don't have access to browse this project"))
        return project

    def get_parent_element(self):
        self.parent_element = None
        if self.kwargs.get("element_id"):
            try:
                self.parent_element = Element.objects.select_related("parent").get(
                    project=self.project, id=self.kwargs["element_id"]
                )
            except Element.DoesNotExist:
                raise Http404(_("No element matching this ID exists on this project"))
            assert self.parent_element.type.folder, _("You can't browse children of a non-folder element")

    def get_queryset(self):
        self.project = self.get_project()
        self.get_parent_element()
        return Element.objects.select_related("project", "type", "image").filter(
            project=self.project, parent=self.parent_element
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["project"] = self.project
        context["parent"] = self.parent_element
        context["can_manage"] = self.has_manager_access(self.project)
        context["total_images"] = Image.objects.filter(elements__project=self.project).distinct().count()
        context["types_counts"] = list(
            Element.objects.filter(project=self.project)
            .values("type__name")
            .annotate(total=Count("type__name"))
            .order_by("-total")
        )
        context["total_elements"] = sum([type_count["total"] for type_count in context["types_counts"]])

        if self.parent_element:
            context["extra_breadcrumb"] = {"title": _("Element"), "link_title": self.parent_element}

        return context


class ProjectCreate(LoginRequiredMixin, CreateView):
    form_class = ProjectManagementForm
    template_name = "project_create.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_anonymous and not request.user.is_staff and not settings.PROJECT_CREATION_ALLOWED:
            raise PermissionDenied(_("You don't have the required rights to create a project"))

        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        # Automatically add the user as a manager of the project
        with transaction.atomic():
            self.object = form.save()
            self.object.memberships.create(user=self.request.user, role=Role.Manager)

        self.object.fetch_extra_info(self.request.user)

        messages.add_message(self.request, messages.SUCCESS, _("The project has been created."))

        return super().form_valid(form)

    def get_success_url(self):
        return reverse("project-details", kwargs={"project_id": self.object.id})


class ProjectDetails(ProjectACLMixin, DetailView):
    model = Project
    template_name = "project_details.html"

    def get_object(self):
        project = super().get_project()
        if not self.has_read_access(project):
            raise PermissionDenied(_("You don't have access to this project details"))

        project.role = (
            None
            if self.user.is_anonymous
            else project.memberships.filter(user=self.user).values_list("role", flat=True).first()
        )
        return project

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["nb_contributors"] = self.object.memberships.filter(role=Role.Contributor).count()

        context["can_manage"] = self.object.role == Role.Manager
        context["can_moderate"] = self.object.role == Role.Moderator

        if self.user.is_anonymous:
            context["campaigns"] = self.object.campaigns.annotate(
                has_available_tasks=Exists(
                    Task.objects.filter(campaign=OuterRef("pk"))
                    .annotate(nb_user_tasks=Count("user_tasks", filter=Q(user_tasks__is_preview=False)))
                    .filter(nb_user_tasks__lt=F("campaign__max_user_tasks"))
                ),
            )
        else:
            user_draft_tasks = TaskUser.objects.filter(user=self.request.user, state=TaskState.Draft).values_list(
                "id", flat=True
            )
            context["campaigns"] = self.object.campaigns.annotate(
                has_available_tasks=Exists(
                    Task.objects.filter(campaign=OuterRef("pk"))
                    .annotate(nb_user_tasks=Count("user_tasks", filter=Q(user_tasks__is_preview=False)))
                    .filter(nb_user_tasks__lt=F("campaign__max_user_tasks"))
                    .exclude(user_tasks__user=self.user)
                ),
                has_pending_tasks=Exists(
                    Task.objects.filter(campaign=OuterRef("pk")).filter(
                        user_tasks__user=self.user, user_tasks__state=TaskState.Pending
                    )
                ),
                has_user_tasks=Exists(
                    Task.objects.filter(campaign=OuterRef("pk"))
                    .filter(user_tasks__user=self.user)
                    .exclude(user_tasks__in=user_draft_tasks)
                ),
            )

        context["campaigns"] = list(
            context["campaigns"]
            # Do not display archived campaigns
            .exclude(state=CampaignState.Archived)
            .annotate(
                # Total tasks are the ones which are truly assigned + ...
                total_tasks=Count("tasks__user_tasks__pk", filter=~Q(tasks__user_tasks__state=TaskState.Draft)),
                # Completed tasks are the one that were interacted with by a contributor and/or a moderator
                completed_tasks=Count(
                    "tasks__user_tasks__pk",
                    filter=~Q(tasks__user_tasks__state__in=[TaskState.Draft, TaskState.Pending]),
                    distinct=True,
                ),
            )
            .order_by("name")
        )

        # TODO: Refactor this part to use a single query. Django doesn't allow "FROM" subqueries,
        # we should try using raw SQL instead, see https://gitlab.teklia.com/callico/callico/-/issues/338
        for campaign in context["campaigns"]:
            # ... + all the remaining assignments on available tasks
            campaign.total_tasks += sum(
                Task.objects.filter(campaign=campaign)
                .annotate(
                    available_assignments=Greatest(
                        campaign.max_user_tasks - Count("user_tasks__pk", filter=Q(user_tasks__is_preview=False)),
                        Value(0),
                    )
                )
                .values_list("available_assignments", flat=True)
            )

        return context


class ProjectUpdate(LoginRequiredMixin, ProjectACLMixin, UpdateView):
    formset = None
    model = Project
    form_class = ProjectManagementForm
    template_name = "project_update.html"

    def get_object(self):
        project = super().get_object()

        # Raise a forbidden error now if user shouldn't access this page
        if not self.has_manager_access(project):
            raise PermissionDenied(_("You don't have the required rights to edit this project"))

        return project

    def form_valid(self, form):
        # Saving the updated information before running the asynchronous task to prevent a race condition
        self.object = form.save()

        self.object.fetch_extra_info(self.request.user)

        messages.add_message(self.request, messages.SUCCESS, _("The project has been edited."))

        return super().form_valid(form)

    def get_success_url(self):
        return reverse("project-details", kwargs={"project_id": self.object.id})


class ProjectMemberList(ProjectACLMixin, LoginRequiredMixin, ListView):
    model = Membership
    paginate_by = 20
    template_name = "project_members/list.html"
    context_object_name = "memberships"

    def get_project(self):
        project = super().get_project()

        # Raise a forbidden error now if user shouldn't access this page
        if not self.has_manager_access(project):
            raise PermissionDenied(_("You don't have the required rights on this project to list its members"))

        return project

    def get_queryset(self):
        self.project = self.get_project()
        return (
            Membership.objects.select_related("user").filter(project=self.project).order_by(Lower("user__display_name"))
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["project"] = self.project
        return context


class ProjectMemberManage(LoginRequiredMixin, ProjectACLMixin):
    form_class = MembershipForm
    template_name = "project_members/manage.html"
    add_kwargs = True

    def get_object(self):
        try:
            membership = Membership.objects.select_related("user").get(id=self.kwargs["pk"])
        except Membership.DoesNotExist:
            raise Http404(_("No membership matching this ID exists"))

        return membership

    def get_project(self):
        project = super().get_project()

        # Raise a forbidden error now if user shouldn't access this page
        if not self.has_manager_access(project):
            raise PermissionDenied(_("You don't have the required rights to %(action)s") % {"action": self.action})

        return project

    def get_form_kwargs(self):
        # Retrieving the project now to raise a forbidden error if user shouldn't access this page
        self.project = self.get_project()
        kwargs = super().get_form_kwargs()
        if self.add_kwargs:
            kwargs["project"] = self.project
        return kwargs

    def cleanup_tasks(self, old_role, new_role=None):
        if new_role and new_role == old_role:
            return

        # Delete draft/pending tasks that are assigned to a former contributor (their role changed or their membership was deleted)
        if old_role == Role.Contributor:
            TaskUser.objects.filter(
                task__campaign__project=self.project,
                state__in=[TaskState.Draft, TaskState.Pending],
                user=self.object.user,
            ).delete()

        # Delete preview tasks that are assigned to a former manager (their role changed or their membership was deleted)
        if old_role == Role.Manager:
            TaskUser.objects.filter(
                task__campaign__project=self.project,
                is_preview=True,
                user=self.object.user,
            ).delete()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["project"] = self.project
        context["action"] = self.template_action
        return context

    def get_success_url(self):
        return reverse("members", kwargs={"project_id": self.project.id})


class ProjectMemberCreate(ProjectMemberManage, CreateView):
    template_action = gettext_lazy("Add")
    template_extra_action = gettext_lazy("Add and create another")

    @property
    def action(self):
        return _("add a new member to this project")

    def form_valid(self, form):
        form.instance.user = form.cleaned_data["user_email"]
        form.instance.project = self.project
        form.instance.role = form.cleaned_data["role"]
        messages.add_message(
            self.request,
            messages.SUCCESS,
            _("The member has been added to this project."),
        )
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["extra_action"] = self.template_extra_action
        context["title"] = _("%(action)s a member to this project") % {"action": self.template_action}
        return context

    def get_success_url(self):
        if self.request.POST.get(self.template_extra_action):
            return reverse("member-create", kwargs={"project_id": self.project.id})

        return super().get_success_url()


class ProjectMemberUpdate(ProjectMemberManage, UpdateView):
    model = Membership
    template_action = gettext_lazy("Edit")

    @property
    def action(self):
        return _("edit this project's members")

    def get_project(self):
        project = super().get_project()

        if self.object.user == self.request.user:
            raise PermissionDenied(_("For security reasons, you are not allowed to edit your own membership"))

        return project

    def form_valid(self, form):
        self.cleanup_tasks(old_role=form.initial["role"], new_role=form.cleaned_data["role"])

        messages.add_message(self.request, messages.SUCCESS, _("The member has been edited."))
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = _("%(action)s a member from this project") % {"action": self.template_action}
        return context


class ProjectMemberDelete(ProjectMemberManage, DeleteView):
    model = Membership
    template_action = gettext_lazy("Delete")
    template_name = "project_members/confirm_delete.html"
    add_kwargs = False

    @property
    def action(self):
        return _("delete this project's members")

    def get_project(self):
        project = super().get_project()

        if self.object.user == self.request.user:
            raise PermissionDenied(_("For security reasons, you are not allowed to delete your own membership"))

        return project

    def get_form_class(self):
        return Form

    def form_valid(self, form):
        self.cleanup_tasks(old_role=self.object.role)

        messages.add_message(
            self.request,
            messages.SUCCESS,
            _("The member has been deleted from this project."),
        )
        return super().form_valid(form)


class InviteLinkManagement(ProjectACLMixin, LoginRequiredMixin, UpdateView):
    model = Project
    template_name = "project_invite_link_management.html"
    fields = []

    def get_object(self):
        project = super().get_project()

        # Raise a forbidden error now if user shouldn't access this page
        if not self.has_manager_access(project):
            raise PermissionDenied(_("You don't have the required rights on this project to manage its invite token"))

        return project

    def form_valid(self, form):
        form.instance.invite_token = generate_token()
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("invite-link-management", kwargs={"project_id": self.object.id})


class ProjectJoin(LoginRequiredMixin, CreateView):
    model = Membership
    fields = []
    template_name = "project_join.html"

    def get_project(self):
        self.project = Project.objects.prefetch_related("memberships").get(invite_token=self.kwargs["invite_token"])

        if self.project.memberships.filter(user_id=self.request.user.id).exists():
            raise BadRequest

        return self.project

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.required_css_class = REQUIRED_CSS_CLASS
        return form

    def form_valid(self, form):
        form.instance.project = self.project
        form.instance.user = self.request.user

        messages.add_message(self.request, messages.SUCCESS, _("You have joined the project as a contributor."))

        return super().form_valid(form)

    def dispatch(self, request, *args, **kwargs):
        try:
            self.get_project()
        except Project.DoesNotExist:
            if request.method == "GET":
                messages.add_message(
                    request,
                    messages.ERROR,
                    _(
                        "The invite link you followed doesn't match any registered project, it might be expired, please contact the manager who provided it."
                    ),
                )

            return HttpResponseRedirect(reverse("projects"))
        except BadRequest:
            if request.method == "GET":
                messages.add_message(
                    request,
                    messages.INFO,
                    _("You clicked on an invitation link to join this project but you already are one of its member."),
                )

            return HttpResponseRedirect(reverse("project-details", kwargs={"project_id": self.project.id}))

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["project"] = self.project
        return context

    def get_success_url(self):
        return reverse("project-details", kwargs={"project_id": self.project.id})


class ElementDetails(LoginRequiredMixin, ProjectACLMixin, DetailView):
    model = Element
    template_name = "element_details.html"

    def get_object(self):
        try:
            element = (
                Element.objects.select_related("project", "type", "image", "provider")
                .prefetch_related("tasks__campaign", "tasks__user_tasks__user")
                .get(id=self.kwargs["pk"])
            )
        except Element.DoesNotExist:
            raise Http404(_("No element matching this ID exists"))

        if not self.has_admin_access(element.project):
            raise PermissionDenied(_("You don't have access to the project of this element and can't see its details"))
        assert not element.type.folder, _("You can't view details of a folder element")

        return element

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["extra_breadcrumb"] = {"title": _("Element"), "link_title": self.object}

        return context


class CampaignCreate(LoginRequiredMixin, ProjectACLMixin, CreateView):
    form_class = CampaignCreateForm
    template_name = "campaign_create.html"

    def form_valid(self, form):
        form.instance.project = self.project
        form.instance.creator = self.request.user

        messages.add_message(self.request, messages.SUCCESS, _("The campaign has been created."))

        return super().form_valid(form)

    def get_form_kwargs(self):
        # Retrieving the project now to raise a forbidden error if user shouldn't access this page
        self.project = self.get_project()
        if not self.has_manager_access(self.project):
            raise PermissionDenied(_("You don't have the required rights to create a campaign on this project"))

        kwargs = super().get_form_kwargs()
        kwargs["project"] = self.project
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["project"] = self.project
        return context

    def get_success_url(self):
        return reverse("campaign-update", kwargs={"pk": self.object.id})


class CampaignDetails(LoginRequiredMixin, ProjectACLMixin, DetailView):
    model = Campaign
    template_name = "campaign_details.html"

    def get_object(self):
        try:
            campaign = Campaign.objects.select_related("project__provider", "creator").get(id=self.kwargs["pk"])
        except Campaign.DoesNotExist:
            raise Http404(_("No campaign matching this ID exists"))

        if not self.has_admin_access(campaign.project):
            raise PermissionDenied(_("You don't have access to this campaign and can't see its details"))

        if campaign.state == CampaignState.Archived:
            raise PermissionDenied(
                _("You cannot view the details of a campaign marked as %(state)s")
                % {"state": campaign.get_state_display()}
            )

        return campaign

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["can_manage"] = self.has_manager_access(self.object.project)

        context["is_exportable_as_csv"] = (
            self.object.state != CampaignState.Created and self.object.mode in CSV_SUPPORTED_CAMPAIGN_MODES
        )
        context["is_exportable_as_xlsx"] = (
            self.object.state != CampaignState.Created and self.object.mode in XLSX_SUPPORTED_CAMPAIGN_MODES
        )
        context["is_exportable_to_arkindex"] = (
            self.object.state != CampaignState.Created
            and self.object.mode in ARKINDEX_PUBLISH_METHODS
            and self.object.project.provider
            and self.object.project.provider.type == ProviderType.Arkindex
            and self.object.project.provider.extra_information.get("worker_run_publication")
        )

        # Compute the median time spent annotating user tasks on this campaign
        context.update(
            Annotation.objects.filter(user_task__task__campaign=self.object).aggregate(
                tracked_median=Median("duration", output_field=DurationField)
            )
        )

        task_qs = Task.objects.filter(campaign=self.object).annotate(
            # We filter out skipped assignments from the "completed" count because they are likely to be reworked (skipped because
            # they were too complicated, the line is empty or for a good reason), so only the most reliable states are kept here.
            completed_assignments=Count(
                "user_tasks__pk",
                filter=Q(user_tasks__is_preview=False)
                & Q(
                    user_tasks__state__in=[state for state in USER_TASK_COMPLETED_STATES if state != TaskState.Skipped]
                ),
            ),
            available_assignments=self.object.max_user_tasks
            - Count("user_tasks__pk", filter=Q(user_tasks__is_preview=False)),
        )

        # Statistics about tasks
        completed_assignments_per_task = list(task_qs.values_list("completed_assignments", flat=True))
        completed_assignments_counts = {
            category: len(list(items))
            for category, items in groupby(sorted(completed_assignments_per_task), lambda x: min(x, 3))
        }
        context["task_counts"] = {
            _("in total\n​"): task_qs.count(),
            _("without completed\nassignment"): completed_assignments_counts.get(0, 0),
            _("with 1 completed\nassignment"): completed_assignments_counts.get(1, 0),
            _("with 2 completed\nassignments"): completed_assignments_counts.get(2, 0),
            _("with 2+ completed\nassignments"): completed_assignments_counts.get(3, 0),
        }

        # Statistics about user tasks
        state_counts = get_user_task_state_counts(task_qs)
        state_counts.pop("total"), state_counts.pop("completed"), state_counts.pop(TaskState.Draft)
        context["available_assignments"] = state_counts.pop(ProgressBarExtraTaskState.Available)
        context["state_counts"] = state_counts

        return context


class CampaignInstructions(LoginRequiredMixin, ProjectACLMixin, DetailView):
    model = Campaign
    template_name = "campaign_instructions.html"

    def get_object(self):
        try:
            campaign = Campaign.objects.select_related("project", "creator").get(id=self.kwargs["pk"])
        except Campaign.DoesNotExist:
            raise Http404(_("No campaign matching this ID exists"))

        if not self.has_read_access(campaign.project):
            raise PermissionDenied(_("You don't have access to this campaign and can't see its details"))

        if campaign.state == CampaignState.Archived:
            raise PermissionDenied(
                _("You cannot view the instructions of a campaign marked as %(state)s")
                % {"state": campaign.get_state_display()}
            )

        return campaign

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["can_admin"] = self.has_admin_access(self.object.project)
        context["has_pending_tasks"] = TaskUser.objects.filter(
            task__campaign=self.object, user=self.request.user, state=TaskState.Pending
        ).exists()
        context["has_available_tasks"] = (
            Task.objects.filter(campaign=self.object)
            .annotate(nb_user_tasks=Count("user_tasks", filter=Q(user_tasks__is_preview=False)))
            .filter(nb_user_tasks__lt=F("campaign__max_user_tasks"))
            .exclude(user_tasks__user=self.user)
            .exists()
        )
        return context


class CampaignUpdate(LoginRequiredMixin, ProjectACLMixin, UpdateView):
    formset = None
    model = Campaign
    template_name = "campaign_configure/base.html"

    def get_object(self):
        try:
            campaign = Campaign.objects.select_related("project").get(id=self.kwargs["pk"])
        except Campaign.DoesNotExist:
            raise Http404(_("No campaign matching this ID exists"))

        if not self.has_manager_access(campaign.project):
            raise PermissionDenied(_("You don't have access to this campaign and can't configure it"))

        if campaign.is_closed:
            raise PermissionDenied(
                _("You cannot configure a campaign marked as %(state)s") % {"state": campaign.get_state_display()}
            )

        return campaign

    def form_valid(self, form):
        configuration = {}

        if self.object.mode == CampaignMode.EntityForm:
            configured_fields = form.instance.configuration.get("fields", [])
            sorted_fields = []

            for group_legend, grouped_fields in groupby(form.cleaned_data.pop("entities_order"), itemgetter(0)):
                grouped_fields = list(grouped_fields)
                # Fields located at the root of the configuration
                if not group_legend:
                    sorted_fields.extend(
                        [
                            find_configured_sorted_field(configured_fields, entity_type, instruction)
                            for (_legend, entity_type, instruction) in grouped_fields
                        ]
                    )
                    continue

                # Fields located in a group
                group = find_configured_sorted_group(configured_fields, group_legend)
                group["fields"] = [
                    find_configured_sorted_field(group["fields"], entity_type, instruction)
                    for (_legend, entity_type, instruction) in grouped_fields
                    if entity_type and instruction
                ]
                sorted_fields.append(group)

            configuration["fields"] = sorted_fields

        configuration.update(
            {key: value for key, value in form.cleaned_data.items() if key not in BaseCampaignUpdateForm.Meta.fields}
        )

        if self.object.mode == CampaignMode.Entity and self.formset:
            # Filter the subforms to completely remove the ones without an entity_type assigned
            configuration["types"] = [
                subform.cleaned_data for subform in self.formset if subform.cleaned_data.get("entity_type")
            ]

        form.instance.configuration.update(configuration)
        form.instance.save()

        messages.add_message(self.request, messages.SUCCESS, _("The campaign has been configured."))

        return super().form_valid(form)

    def get_form_class(self):
        return CAMPAIGN_UPDATE_FORMS.get(self.object.mode, ContextualizedCampaignUpdateForm)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if self.object.mode == CampaignMode.Entity and not self.formset:
            formset_args = (
                # Simply retrieve the information sent
                {"data": self.request.POST}
                if self.request.POST
                # Pre-fill the forms with the existing values
                else {"initial": self.object.configuration.get("types", [])}
            )
            FormSetFactory = formset_factory(EntityCampaignUpdateFormset, extra=0)
            self.formset = FormSetFactory(**formset_args)

        context["formset"] = self.formset

        if self.object.mode == CampaignMode.EntityForm:
            context["authorities"] = {str(authority.id): authority.name for authority in Authority.objects.all()}

        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()

        # Update formset attribute
        self.get_context_data()

        formset_is_valid = True
        # Each form of the Entity formset should be unique
        if self.object.mode == CampaignMode.Entity and self.formset:
            # Subform validation for Entity campaign configuration only validates the entity_type:
            # that it is present (if not, the subform is ignored) and unique within the campaign.
            # Multiple entity types can have the same entity_color.
            formset_values = [
                subform.cleaned_data["entity_type"]
                for subform in self.formset
                if subform.is_valid() and subform.cleaned_data
            ]
            for subform in self.formset:
                if formset_values.count(subform.cleaned_data.get("entity_type")) > 1:
                    subform.add_error("entity_type", _("There are several forms with these values"))
                    formset_is_valid = False

        if form.is_valid() and formset_is_valid:
            return self.form_valid(form)

        return self.form_invalid(form)

    def get_success_url(self):
        return reverse("campaign-details", kwargs={"pk": self.object.id})


class EntityFormObjectManage(LoginRequiredMixin, ProjectACLMixin, FormView):
    add_kwargs = True
    template_name = "campaign_configure/entity_form_object_manage.html"

    @property
    def is_field_group(self):
        return self.request.GET.get("mode") == ENTITY_FORM_GROUP_MODE

    @property
    def template_object(self):
        return _("field group") if self.is_field_group else _("field")

    @property
    def template_object_plural(self):
        return _("field groups") if self.is_field_group else _("fields")

    def get_campaign(self):
        try:
            campaign = Campaign.objects.select_related("project").get(
                id=self.kwargs["pk"], mode=CampaignMode.EntityForm
            )
        except Campaign.DoesNotExist:
            raise Http404(_("No EntityForm campaign matching this ID exists"))

        if not self.has_manager_access(campaign.project):
            raise PermissionDenied(
                _("You don't have access to this campaign and can't %(action)s") % {"action": self.action_access}
            )

        if campaign.is_closed:
            raise PermissionDenied(
                _("You cannot %(action)s on a campaign marked as %(state)s")
                % {"action": self.action_closed, "state": campaign.get_state_display()}
            )

        return campaign

    def get_configured_object(self):
        self.campaign = self.get_campaign()

        self.position = self.kwargs["position"]
        self.current_group = int(self.request.GET.get("group", -1))

        search_in = self.campaign.configuration.get("fields", [])
        if self.current_group >= 0:
            if (
                self.current_group >= len(search_in)
                or search_in[self.current_group].get("mode") != ENTITY_FORM_GROUP_MODE
            ):
                raise Http404(_("The group to search your field in does not exist in your campaign"))

            search_in = search_in[self.current_group]["fields"]

        if self.position >= len(search_in):
            raise Http404(
                _("No %(object)s matching this position exists in your campaign") % {"object": self.template_object}
            )

        return search_in[self.position]

    def get_form_class(self):
        return EntityFormGroupForm if self.is_field_group else EntityFormFieldForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()

        if self.add_kwargs:
            kwargs["initial"] = self.get_configured_object()
            kwargs["campaign"] = self.campaign
            kwargs["position"] = self.position
            kwargs["group"] = self.current_group

        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["campaign"] = self.campaign
        context["display_configuration"] = True
        context["action"] = self.template_action
        context["obj"] = self.template_object
        context["is_field_group"] = self.is_field_group
        return context

    def get_success_url(self):
        return reverse("campaign-update", kwargs={"pk": self.campaign.id})


class EntityFormObjectCreate(EntityFormObjectManage):
    template_action = gettext_lazy("Add")
    template_extra_action = gettext_lazy("Add and create another")

    @property
    def action_access(self):
        return _("add a new %(object)s on it") % {"object": self.template_object}

    @property
    def action_closed(self):
        return _("add a new %(object)s") % {"object": self.template_object}

    def get_configured_object(self):
        self.campaign = self.get_campaign()
        self.position = None
        self.current_group = None
        return {}

    def form_valid(self, form):
        created_group = int(form.cleaned_data.pop("group", -1))

        if created_group < 0:
            self.campaign.configuration["fields"] = [*self.campaign.configuration.get("fields", []), form.cleaned_data]
        else:
            self.campaign.configuration["fields"][created_group]["fields"] = [
                *self.campaign.configuration["fields"][created_group]["fields"],
                form.cleaned_data,
            ]
        self.campaign.save()

        messages.add_message(
            self.request,
            messages.SUCCESS,
            _("The form %(object)s has been added.") % {"object": self.template_object},
        )

        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["extra_action"] = self.template_extra_action
        return context

    def get_success_url(self):
        success_url = super().get_success_url()

        if self.request.POST.get(self.template_extra_action):
            success_url = (
                reverse("entity-form-object-create", kwargs={"pk": self.campaign.id})
                + f'?mode={self.request.GET.get("mode", "field")}'
            )

        return success_url


class EntityFormObjectUpdate(EntityFormObjectManage):
    template_action = gettext_lazy("Edit")

    @property
    def action_access(self):
        return _("edit its %(object)s") % {"object": self.template_object_plural}

    @property
    def action_closed(self):
        return _("edit %(object)s") % {"object": self.template_object_plural}

    def form_valid(self, form):
        updated_group = int(form.cleaned_data.pop("group", -1))

        source_fields = (
            self.campaign.configuration["fields"]
            if self.current_group < 0
            else self.campaign.configuration["fields"][self.current_group]["fields"]
        )
        # Not moved (from root, from group)
        if self.current_group == updated_group:
            source_fields[self.position] = form.cleaned_data
        # Moved (from root to a group, from a group to root, from a group to another group)
        else:
            dest_fields = (
                self.campaign.configuration["fields"]
                if updated_group < 0
                else self.campaign.configuration["fields"][updated_group]["fields"]
            )
            dest_fields.append(form.cleaned_data)

            source_fields.pop(self.position)

        self.campaign.save()

        messages.add_message(
            self.request, messages.SUCCESS, _("The form %(object)s has been edited.") % {"object": self.template_object}
        )

        return super().form_valid(form)


class EntityFormObjectDelete(EntityFormObjectManage, BaseDeleteView):
    template_action = gettext_lazy("Delete")

    add_kwargs = False
    template_name = "campaign_configure/entity_form_object_confirm_delete.html"

    @property
    def action_access(self):
        return _("delete its %(object)s") % {"object": self.template_object_plural}

    @property
    def action_closed(self):
        return _("delete %(object)s") % {"object": self.template_object_plural}

    def get_form_class(self):
        return Form

    def get_object(self):
        self.field = self.get_configured_object()
        return self.field["legend"] if self.is_field_group else self.field["instruction"]

    def form_valid(self, form):
        # When a group is deleted, all its fields are appended to the root
        if self.is_field_group:
            self.campaign.configuration["fields"] = self.campaign.configuration["fields"] + self.field["fields"]

        source_fields = (
            self.campaign.configuration["fields"]
            if self.current_group < 0
            else self.campaign.configuration["fields"][self.current_group]["fields"]
        )
        source_fields.pop(self.position)

        self.campaign.save()

        messages.add_message(
            self.request,
            messages.SUCCESS,
            _("The form %(object)s has been deleted.") % {"object": self.template_object},
        )

        return HttpResponseRedirect(self.get_success_url())


class CampaignUpdateState(LoginRequiredMixin, ProjectACLMixin, View):
    def get_campaign(self):
        try:
            campaign = Campaign.objects.select_related("project").get(id=self.kwargs["pk"])
        except Campaign.DoesNotExist:
            raise Http404(_("No campaign matching this ID exists"))

        if not self.has_manager_access(campaign.project):
            raise PermissionDenied(_("You don't have access to this campaign and can't update its state"))

        if campaign.state == CampaignState.Archived:
            raise PermissionDenied(
                _("You cannot update the state of a campaign marked as %(state)s")
                % {"state": campaign.get_state_display()}
            )

        return campaign

    def post(self, request, *args, **kwargs):
        campaign = self.get_campaign()

        if "reopen" in request.POST:
            campaign.state = CampaignState.Running
            messages.add_message(
                self.request, messages.SUCCESS, _("The campaign has been reopened and marked as running.")
            )
        elif "close" in request.POST:
            campaign.state = CampaignState.Closed
            messages.add_message(
                self.request, messages.SUCCESS, _("The campaign has been closed and marked as completed.")
            )
        elif "archive" in request.POST:
            campaign.state = CampaignState.Archived
            messages.add_message(self.request, messages.SUCCESS, _("The campaign has been archived."))

        campaign.save()

        return (
            HttpResponseRedirect(reverse("project-details", kwargs={"project_id": campaign.project.id}))
            if "archive" in request.POST
            else HttpResponseRedirect(reverse("campaign-details", kwargs={"pk": campaign.id}))
        )


class CampaignTasksCreate(LoginRequiredMixin, ProjectACLMixin, FormView):
    form_class = CampaignTasksCreateForm
    template_name = "campaign_tasks_create.html"
    preview_task = None
    preview_user_task = None

    def get_campaign(self):
        try:
            self.campaign = Campaign.objects.select_related("project").get(id=self.kwargs["pk"])
        except Campaign.DoesNotExist:
            raise Http404(_("No campaign matching this ID exists"))

        # Raise a forbidden error now if user shouldn't access this page
        if not self.has_manager_access(self.campaign.project):
            raise PermissionDenied(_("You don't have the required rights to create tasks on this project"))

        if self.campaign.is_closed:
            raise PermissionDenied(
                _("You cannot create tasks for a campaign marked as %(state)s")
                % {"state": self.campaign.get_state_display()}
            )

        if not self.campaign.project.elements.filter(image__isnull=False).exists():
            raise Http404(_("You cannot create tasks for a project that does not contain images"))

        return self.campaign

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["campaign"] = self.get_campaign()
        kwargs["request"] = self.request
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["campaign"] = self.campaign
        if self.campaign.mode == CampaignMode.Transcription:
            filters = {}

            conf_types = self.campaign.configuration.get("children_types")
            if conf_types:
                filters["id__in"] = conf_types
            else:
                filters["folder"] = False

            context["children_types"] = (
                self.campaign.project.types.filter(**filters).order_by("name").values_list("name", flat=True)
            )

        return context

    def form_valid(self, form):
        element_type = form.cleaned_data.get("type")
        users = form.cleaned_data.get("users")
        algorithm = form.cleaned_data.get("algorithm")

        order_fields = {ALGORITHM_RANDOM: ["?"], ALGORITHM_SEQUENTIAL: ["parent_id", "order"]}
        elements = self.campaign.project.elements.filter(type_id=element_type).order_by(
            *order_fields.get(algorithm, [])
        )

        # Exclude already used elements
        element_selection = form.cleaned_data.get("element_selection")
        if element_selection == ELEMENT_SELECTION_UNUSED:
            assigned_tasks = self.campaign.tasks.filter(user_tasks__isnull=False).values_list("id", flat=True)
            elements = elements.exclude(tasks__in=assigned_tasks)

        # The manager hit the "Preview" button not the "Create" one
        if "preview" in self.request.POST:
            self.preview_task, _created = Task.objects.get_or_create(campaign=self.campaign, element=elements[0])
            self.preview_user_task, _created = TaskUser.objects.get_or_create(
                user=self.request.user,
                task=self.preview_task,
                defaults={"state": TaskState.Pending, "is_preview": True},
            )
            return super().form_valid(form)

        elements = list(elements)
        elements_to_use = elements
        self.elements_not_to_use = []

        users_count = users.count()

        # Limit the number of tasks per user
        max_number = form.cleaned_data.get("max_number")
        if max_number:
            elements_to_use = elements_to_use[: max_number * users_count]

            create_unassigned_tasks = form.cleaned_data.get("create_unassigned_tasks")
            if create_unassigned_tasks:
                self.elements_not_to_use = elements[max_number * users_count :]

        Task.objects.bulk_create(
            [Task(campaign=self.campaign, element=element) for element in elements_to_use + self.elements_not_to_use],
            ignore_conflicts=True,
        )

        # This could happen if no user was selected and that unassigned tasks creation was requested
        # we skip this step to avoid errors since there is no one to assign on selected elements
        if not users_count:
            self.nb_usertasks = 0
            return super().form_valid(form)

        # Retrieve existing and/or created tasks and preserve the order of elements for the use
        cases = [When(element=element, then=i) for i, element in enumerate(elements_to_use)]
        tasks = (
            Task.objects.filter(campaign=self.campaign, element__in=elements_to_use)
            .annotate(order=Case(*cases, output_field=IntegerField()))
            .order_by("order")
        )

        nb_tasks = len(tasks)
        nb_tasks_by_user = math.ceil(nb_tasks / users_count)
        self.nb_usertasks = len(
            TaskUser.objects.bulk_create(
                [
                    TaskUser(user=user, task=task)
                    for user, batch in zip(users, range(0, nb_tasks, nb_tasks_by_user))
                    for task in tasks[batch : batch + nb_tasks_by_user]
                ],
                ignore_conflicts=True,
            )
        )

        if self.preview_task:
            if self.preview_user_task.state == TaskState.Validated:
                messages.add_message(self.request, messages.WARNING, _("Can't annotate a validated preview task."))
            elif not self.preview_user_task.annotate_url:
                messages.add_message(
                    self.request,
                    messages.WARNING,
                    _("The annotation for the campaign mode of the preview task is not yet implemented."),
                )
        else:
            message_unassigned_tasks = (
                _("%(count)s tasks were created or already existing") % {"count": len(self.elements_not_to_use)}
                if self.elements_not_to_use
                else ""
            )
            message_assigned_tasks = (
                _("%(count)s tasks assigned to the selected users were created or already existing")
                % {"count": self.nb_usertasks}
                if self.nb_usertasks
                else ""
            )
            message = (
                "{} {} {}".format(message_unassigned_tasks, _("and"), message_assigned_tasks)
                if message_unassigned_tasks and message_assigned_tasks
                else message_unassigned_tasks or message_assigned_tasks
            )
            messages.add_message(self.request, messages.SUCCESS, f"{message}.")

        return super().form_valid(form)

    def get_success_url(self):
        if (
            self.preview_task
            and self.preview_user_task.state != TaskState.Validated
            and self.preview_user_task.annotate_url
        ):
            return self.preview_user_task.annotate_url

        if self.preview_task:
            query_params = f"user_id={self.preview_user_task.user.id}"
        elif self.nb_usertasks:
            query_params = f"state={TaskState.Draft}"
        else:
            query_params = f"user_id={NO_USER}"

        return reverse("admin-campaign-task-list", kwargs={"pk": self.campaign.id}) + f"?{query_params}"


class PublishDraftTasks(LoginRequiredMixin, ProjectACLMixin, UpdateView):
    model = Campaign
    fields = []

    def get_object(self):
        try:
            campaign = Campaign.objects.select_related("project").get(id=self.kwargs["pk"])
        except Campaign.DoesNotExist:
            raise Http404(_("No campaign matching this ID exists"))

        if not self.has_manager_access(campaign.project):
            raise PermissionDenied(_("You don't have access to this campaign and can't publish draft tasks from it"))

        if campaign.is_closed:
            raise PermissionDenied(
                _("You cannot publish draft tasks for a campaign marked as %(state)s")
                % {"state": campaign.get_state_display()}
            )

        return campaign

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.required_css_class = REQUIRED_CSS_CLASS
        return form

    def form_valid(self, form):
        draft_tasks = TaskUser.objects.filter(task__campaign=self.object, state=TaskState.Draft)
        users = list(User.objects.filter(user_tasks__in=draft_tasks).distinct())

        # Mark as Draft tasks as Pending
        draft_tasks.update(state=TaskState.Pending)

        # Start the campaign if it wasn't the case before
        self.object.state = CampaignState.Running

        context = {
            "my_tasks_url": urljoin(
                settings.INSTANCE_URL, reverse("contributor-campaign-task-list", kwargs={"pk": self.object.id})
            ),
        }
        # Send an email to notify that new tasks were assigned
        for user in users:
            with translation.override(user.preferred_language):
                message = render_to_string("mails/new_tasks.html", context=context)
                send_email.delay(
                    _("New annotation tasks for the project %(project)s - Callico") % {"project": self.object.project},
                    message,
                    [user.email],
                )

        return super().form_valid(form)

    def get_success_url(self):
        return reverse("admin-campaign-task-list", kwargs={"pk": self.object.id})


class CampaignJoin(LoginRequiredMixin, SingleObjectMixin, View):
    """
    Allow a user to contribute to the campaign of a project.
    Automatically assign up to Campaign.nb_tasks_auto_assignment free tasks.
    If not a member of the project, the user will be added as a contributor.
    """

    queryset = Campaign.objects.select_related("project")

    def post(self, request, *args, **kwargs):
        campaign = self.get_object()
        user = request.user

        if campaign.is_closed:
            raise PermissionDenied(
                _("You cannot request tasks from a campaign marked as %(state)s")
                % {"state": campaign.get_state_display()}
            )

        pending_tasks = Task.objects.filter(
            campaign=campaign, user_tasks__user=user, user_tasks__state=TaskState.Pending
        )
        if pending_tasks.exists():
            raise BadRequest(_("You already have pending tasks on this campaign"))

        # List available tasks in the same order than the sequential algorithm
        # used for creation, up to Campaign.nb_tasks_auto_assignment
        available_tasks = (
            Task.objects.filter(campaign=campaign)
            .annotate(nb_user_tasks=Count("user_tasks", filter=Q(user_tasks__is_preview=False)))
            .filter(nb_user_tasks__lt=campaign.max_user_tasks)
            .order_by("nb_user_tasks", "element__parent_id", "element__order")
            .values_list("id", flat=True)
        )

        task_id = self.request.POST.get("task_id")

        if not task_id and not campaign.nb_tasks_auto_assignment:
            raise BadRequest(_("The campaign does not allow to request tasks"))

        tasks = (
            [available_task_id for available_task_id in available_tasks if str(available_task_id) == task_id]
            if task_id
            else list(available_tasks.exclude(user_tasks__user=user))[: campaign.nb_tasks_auto_assignment]
        )
        tasks_count = len(tasks)
        if not tasks_count:
            raise BadRequest(_("All tasks on this campaign are already assigned"))

        membership, new_member = campaign.project.memberships.get_or_create(
            user=user, defaults={"role": Role.Contributor}
        )
        if membership.role != Role.Contributor:
            raise PermissionDenied(_("Only contributors can request tasks"))

        created_user_tasks = TaskUser.objects.bulk_create(
            [TaskUser(task_id=task_id, user=user, state=TaskState.Pending) for task_id in tasks]
        )

        # Start the campaign if it wasn't the case before
        campaign.state = CampaignState.Running
        campaign.save()

        # Send an email to the project managers to alert them that all unassigned tasks have been requested
        if not available_tasks.all().exists():
            context = {
                "campaign_name": campaign.name,
                "project_name": campaign.project.name,
                "campaign_details_url": urljoin(
                    settings.INSTANCE_URL,
                    reverse("campaign-details", kwargs={"pk": campaign.id}),
                ),
            }
            managers = User.objects.filter(memberships__project=campaign.project, memberships__role=Role.Manager)
            for manager in managers:
                with translation.override(manager.preferred_language):
                    message = render_to_string("mails/no_more_available_tasks.html", context=context)
                    send_email.delay(
                        _("All available tasks on the campaign %(campaign)s have been requested - Callico")
                        % {"campaign": campaign.name},
                        message,
                        [manager.email],
                    )

        msg = ""
        if new_member:
            msg = _("You are now contributor on project %(name)s. ") % {"name": campaign.project.name}
        msg += _("%(count)s tasks have been assigned to you.") % {"count": tasks_count}
        messages.add_message(self.request, messages.SUCCESS, msg)

        return HttpResponseRedirect(created_user_tasks[0].annotate_url + f"?state={TaskState.Pending}")


class BaseCampaignTasksList(ProjectACLMixin, FormFilteredListView):
    model = Task
    paginate_by = 20
    context_object_name = "tasks"

    queryset = Task.objects.select_related("campaign", "element__type").distinct()

    def get_campaign(self):
        try:
            self.campaign = Campaign.objects.select_related("project").get(id=self.kwargs["pk"])
        except Campaign.DoesNotExist:
            raise Http404(_("No campaign matching this ID exists"))

        return self.campaign

    def get_queryset(self):
        qs = super().get_queryset()
        # Always filter the queryset by campaign
        return qs.filter(campaign_id=self.campaign.id).annotate(
            nb_comments=Count("comments", distinct=True), last_comment=Max("comments__created")
        )

    def filter_queryset(self, qs, **filters):
        query_filters = {}

        state = filters.get("state")
        if state == USER_TASK_AVAILABLE_STATE:
            # "available" isn't a correct filtering value for the "state" attribute
            del filters["state"]

        user_id = filters.get("user_id")
        if user_id == NO_USER:
            query_filters["user_tasks__isnull"] = True
        else:
            user_feedback = filters.pop("user_feedback")

            filters["task__campaign_id"] = self.campaign.id
            if user_feedback in [USER_TASK_UNCERTAIN_FEEDBACK, USER_TASK_ALL_FEEDBACKS]:
                filters["has_uncertain_value"] = True
            if user_feedback in [USER_TASK_WITH_COMMENTS, USER_TASK_ALL_FEEDBACKS]:
                filters["task__comments__isnull"] = False
            if user_feedback == USER_TASK_NO_FEEDBACK:
                filters["has_uncertain_value"] = False
                filters["task__comments__isnull"] = True

            # The order is the same as when annotating/modifying tasks
            # Without this order, the list would not be consistent with the navigation during annotation/moderation
            user_tasks = super().filter_queryset(TaskUser.objects, **filters).order_by("created", "id").distinct()

            # Do not filter the user_tasks according to the user_id
            if state == USER_TASK_AVAILABLE_STATE:
                user_tasks = TaskUser.objects.none()
            elif not user_tasks or self.user.is_anonymous:
                return Task.objects.none()

            query_filters["user_tasks__in"] = user_tasks
            qs = qs.prefetch_related(Prefetch("user_tasks", queryset=user_tasks))

        if state == USER_TASK_AVAILABLE_STATE:
            if user_id and user_id != NO_USER:
                qs = qs.exclude(user_tasks__user_id=user_id)
            qs = qs.annotate(nb_user_tasks=Count("user_tasks", filter=Q(user_tasks__is_preview=False)))
            query_filters["nb_user_tasks__lt"] = self.campaign.max_user_tasks

        return (
            super()
            .filter_queryset(qs, **query_filters)
            .prefetch_related("user_tasks__user", "element")
            # The order is the same as when annotating/modifying tasks
            # Without this order, the list would not be consistent with the navigation during annotation/moderation
            .order_by("created", "id")
        )

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["campaign"] = self.get_campaign()
        return kwargs

    def get_progress_bar_qs(self):
        return Task.objects.none().annotate(available_assignments=Value(0))

    def get_counts(self):
        return {}

    def get_progression(self):
        counts = self.get_counts()

        total = counts.pop("total", 0) + counts[ProgressBarExtraTaskState.Available]
        if not total:
            return {}

        completed = counts.pop("completed", 0)
        return {
            "total": total,
            "completed": completed,
            "details": [
                {
                    "state": state,
                    "nb_tasks": counts[state],
                    "display": True,
                    "apply_filter": "state"
                    if state in TaskState or state == USER_TASK_AVAILABLE_STATE
                    else "user_feedback",
                }
                for state in PROGRESS_BAR_ORDER
                if state in counts
            ],
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["progression"] = self.get_progression()
        context["campaign"] = self.campaign

        return context


class AdminCampaignTasksList(LoginRequiredMixin, BaseCampaignTasksList):
    form_class = AdminCampaignTasksListForm
    template_name = "campaign_task_list_admin.html"

    def get_campaign(self):
        self.campaign = super().get_campaign()

        # Raise a forbidden error now if user shouldn't access this page
        if not self.has_admin_access(self.campaign.project):
            raise PermissionDenied(_("You don't have the required rights on this project to list tasks"))

        if self.campaign.state == CampaignState.Archived:
            raise PermissionDenied(
                _("You cannot list the tasks of a campaign marked as %(state)s")
                % {"state": self.campaign.get_state_display()}
            )

        return self.campaign

    def get_progress_bar_qs(self):
        user_id_param = self.request.GET.get("user_id")
        if user_id_param == NO_USER:
            return super().get_progress_bar_qs()

        user_filter = {"user_tasks__user_id": user_id_param} if user_id_param else {}
        qs = Task.objects.filter(campaign=self.campaign, **user_filter)
        if user_filter:
            return qs.annotate(available_assignments=Value(0))
        else:
            return qs.annotate(
                available_assignments=self.campaign.max_user_tasks
                - Count("user_tasks__pk", filter=Q(user_tasks__is_preview=False))
            )

    def get_counts(self):
        progress_bar_qs = self.get_progress_bar_qs()

        return get_user_task_state_counts(progress_bar_qs)


class ContributorCampaignTasksList(BaseCampaignTasksList):
    form_class = ContributorCampaignTasksListForm
    template_name = "campaign_task_list_contributor.html"

    def get_campaign(self):
        self.campaign = super().get_campaign()

        # Raise a forbidden error now if user shouldn't access this page
        has_public_available_tasks = self.campaign.project.public and (
            Task.objects.annotate(nb_user_tasks=Count("user_tasks", filter=Q(user_tasks__is_preview=False)))
            .filter(campaign=self.campaign, nb_user_tasks__lt=F("campaign__max_user_tasks"))
            .exists()
        )
        if not (
            # An anonymous user can access this page if there are available tasks on a public project
            (self.user.is_anonymous and has_public_available_tasks)
            or (
                # A logged user can access this page if...
                not self.user.is_anonymous
                and (
                    # ... they are a contributor
                    self.has_contributor_access(self.campaign.project)
                    # ... they are not an admin and there are available tasks on a public project
                    or (not self.has_admin_access(self.campaign.project) and has_public_available_tasks)
                )
            )
        ):
            raise PermissionDenied(_("You don't have the required rights on this project to list your own tasks"))

        if self.campaign.is_closed:
            raise PermissionDenied(
                _("You cannot list the tasks of a campaign marked as %(state)s")
                % {"state": self.campaign.get_state_display()}
            )

        return self.campaign

    def filter_queryset(self, qs, **filters):
        if not self.user.is_anonymous:
            filters["user_id"] = self.request.user.id

        qs = super().filter_queryset(qs, **filters)

        user_draft_tasks = (
            TaskUser.objects.filter(
                task__campaign=self.campaign, user=self.request.user, state=TaskState.Draft
            ).values_list("id", flat=True)
            if not self.user.is_anonymous
            else []
        )
        return qs.exclude(user_tasks__in=user_draft_tasks).select_related("campaign").prefetch_related("element__image")

    def get_progress_bar_qs(self):
        return Task.objects.filter(campaign=self.campaign).annotate(
            available_assignments=self.campaign.max_user_tasks
            - Count("user_tasks__pk", filter=Q(user_tasks__is_preview=False))
        )

    def get_counts(self):
        progress_bar_qs = self.get_progress_bar_qs()
        counts = progress_bar_qs.filter(user_tasks__user=self.user).aggregate(
            total=Count("user_tasks__pk", filter=~Q(user_tasks__state=TaskState.Draft)),
            completed=Count("user_tasks__pk", filter=Q(user_tasks__state__in=USER_TASK_COMPLETED_STATES)),
            **{state: Count("user_tasks__pk", filter=Q(user_tasks__state=state)) for state in TaskState},
            uncertain=Count("user_tasks__pk", filter=Q(user_tasks__has_uncertain_value=True)),
        )

        counts.update(
            {
                ProgressBarExtraTaskState.Available: progress_bar_qs.exclude(user_tasks__user=self.user)
                .filter(available_assignments__gt=0)
                .count()
            }
        )

        return counts

    def get_progression(self):
        # Special (simpler) query for anonymous users
        if self.user.is_anonymous or not self.campaign.project.memberships.filter(user=self.user).exists():
            available_count = self.get_progress_bar_qs().filter(available_assignments__gt=0).count()
            return {
                "total": 0,
                "completed": 0,
                "details": [{"state": ProgressBarExtraTaskState.Available, "nb_tasks": available_count}],
            }

        progression = super().get_progression()
        if not progression:
            return progression

        for state_progress in progression["details"]:
            if state_progress["state"] == ProgressBarExtraTaskState.Available:
                # Display the number of available tasks in the tabulation but not in the progress bar
                progression["total"] -= state_progress["nb_tasks"]
                state_progress["display"] = False
                # Update the order of the list
                progression["details"].remove(state_progress)
                progression["details"].insert(0, state_progress)
            elif state_progress["state"] == ProgressBarExtraTaskState.Uncertain:
                # Display the number of uncertain tasks in the tabulation but not in the progress bar
                state_progress["display"] = False

        return progression

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["has_pending_tasks"] = next(
            (
                state_progress["nb_tasks"]
                for state_progress in context.get("progression", {}).get("details", [])
                if state_progress["state"] == TaskState.Pending
            ),
            0,
        )

        return context


class CampaignTasksUnassign(LoginRequiredMixin, ProjectACLMixin, ListView):
    model = User
    paginate_by = 20
    template_name = "campaign_tasks_unassign.html"
    context_object_name = "users"

    def get_campaign(self):
        try:
            self.campaign = Campaign.objects.select_related("project").get(id=self.kwargs["pk"])
        except Campaign.DoesNotExist:
            raise Http404(_("No campaign matching this ID exists"))

        # Raise a forbidden error now if user shouldn't access this page
        if not self.has_manager_access(self.campaign.project):
            raise PermissionDenied(_("You don't have the required rights to unassign tasks on this project"))

        if self.campaign.state == CampaignState.Archived:
            raise PermissionDenied(
                _("You cannot unassign tasks on a campaign marked as %(state)s")
                % {"state": self.campaign.get_state_display()}
            )

        return self.campaign

    def get_queryset(self):
        self.get_campaign()

        return (
            User.objects.annotate(
                pending_user_tasks_count=Count(
                    "user_tasks",
                    filter=Q(user_tasks__state=TaskState.Pending, user_tasks__task__campaign=self.campaign),
                ),
                draft_user_tasks_count=Count(
                    "user_tasks",
                    filter=Q(user_tasks__state=TaskState.Draft, user_tasks__task__campaign=self.campaign),
                ),
                last_annotation=Max(
                    "user_tasks__annotations__created", filter=Q(user_tasks__task__campaign=self.campaign)
                ),
            )
            .filter(Q(pending_user_tasks_count__gt=0) | Q(draft_user_tasks_count__gt=0))
            .order_by("email")
        )

    def post(self, request, *args, **kwargs):
        # Delete unassigned tasks
        if "unassigned" in request.POST:
            self.get_campaign()

            deleted_count, deleted = self.campaign.tasks.filter(user_tasks__isnull=True).delete()
            messages.add_message(
                request,
                messages.SUCCESS,
                _("%(count)s unassigned tasks have been deleted.") % {"count": deleted_count},
            )

            return self.get(request, *args, **kwargs)

        # Unassign tasks of a specific user
        try:
            user = self.get_queryset().get(id=self.request.POST.get("user_id"))
        except User.DoesNotExist:
            raise Http404(_("No user matching this ID has draft or pending tasks on this campaign"))

        state = TaskState.Pending if "pending" in request.POST else TaskState.Draft
        unassign_count, deleted = user.user_tasks.filter(state=state, task__campaign=self.campaign).delete()

        messages.add_message(
            request,
            messages.SUCCESS,
            _("%(count)s tasks have been unassigned from user %(user)s.") % {"count": unassign_count, "user": user},
        )

        return self.get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["campaign"] = self.campaign
        context["nb_unassigned_tasks"] = self.campaign.tasks.filter(user_tasks__isnull=True).count()
        return context
