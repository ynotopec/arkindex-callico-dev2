import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http.response import Http404, HttpResponseRedirect
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.generic import DetailView, ListView, View

from callico.process.models import Process, ProcessMode
from callico.process.tasks import csv_export, xlsx_export
from callico.projects.mixins import ProjectACLMixin
from callico.projects.models import (
    CSV_SUPPORTED_CAMPAIGN_MODES,
    XLSX_SUPPORTED_CAMPAIGN_MODES,
    Campaign,
    CampaignState,
    Project,
)

logger = logging.getLogger(__name__)


class ProcessList(LoginRequiredMixin, ProjectACLMixin, ListView):
    model = Process
    paginate_by = 20
    template_name = "process_list.html"
    context_object_name = "processes"

    def get_project(self):
        try:
            project = Project.objects.get(id=self.kwargs["pk"])
        except Project.DoesNotExist:
            raise Http404(_("No project matching this ID exists"))

        # Raise a forbidden error now if user shouldn't access this page
        if not self.has_manager_access(project):
            raise PermissionDenied(_("You don't have the required rights on this project to list processes"))

        return project

    def get_queryset(self):
        self.project = self.get_project()
        return Process.objects.filter(project=self.project).select_related("creator").order_by("-created")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["project"] = self.project
        return context


class ProcessDetails(LoginRequiredMixin, ProjectACLMixin, DetailView):
    model = Process
    template_name = "process_details.html"

    def get_object(self):
        try:
            process = Process.objects.select_related("project", "creator").get(id=self.kwargs["pk"])
        except Process.DoesNotExist:
            raise Http404(_("No process matching this ID exists"))

        if not self.has_manager_access(process.project):
            raise PermissionDenied(_("You don't have access to this process and can't see its details"))

        return process

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["extra_breadcrumb"] = {"title": _("Process"), "link_title": self.object}

        logs_level = [log["level"] for log in self.object.parsed_logs]
        context["logs_stats"] = {
            level: {"name": logging.getLevelName(level), "count": logs_level.count(level)}
            for level in [logging.ERROR, logging.WARNING, logging.INFO, logging.DEBUG]
            if logger.isEnabledFor(level)
        }
        context["filtered_level"] = self.request.GET.get("level")

        return context

    def post(self, request, *args, **kwargs):
        process = self.get_object()
        process.stop(request.user)
        return HttpResponseRedirect(reverse("process-details", kwargs={"pk": process.id}))


class BaseFileExportProcessCreate(LoginRequiredMixin, ProjectACLMixin, View):
    def get_campaign(self):
        try:
            campaign = Campaign.objects.select_related("project").get(id=self.kwargs["pk"])
        except Campaign.DoesNotExist:
            raise Http404(_("No campaign matching this ID exists"))

        if not self.has_manager_access(campaign.project):
            raise PermissionDenied(
                _("You don't have access to this campaign and can't export its results as %(format)s")
                % {"format": self.file_format}
            )

        if campaign.state == CampaignState.Archived:
            raise PermissionDenied(
                _("You cannot export results as %(format)s from a campaign marked as %(state)s")
                % {"format": self.file_format, "state": campaign.get_state_display()}
            )

        if campaign.mode not in self.supported_campaign_modes:
            raise Http404(
                _("You cannot export results as %(format)s for a campaign of type %(mode)s")
                % {"format": self.file_format, "mode": campaign.get_mode_display()}
            )

        return campaign

    def post(self, request, *args, **kwargs):
        campaign = self.get_campaign()
        name = f"{self.file_format} export for {campaign.name}"
        trunc_name = f"{name[:509]}..." if len(name) > 512 else name
        process = Process.objects.create(
            name=trunc_name,
            mode=self.process_mode,
            project=campaign.project,
            creator=request.user,
            configuration={
                "campaign_id": str(campaign.id),
            },
        )

        self.celery_task.apply_async(kwargs=process.configuration, task_id=str(process.id))

        messages.add_message(
            self.request,
            messages.SUCCESS,
            _("The process to export the campaign results as %(format)s has been started.")
            % {"format": self.file_format},
        )
        return HttpResponseRedirect(reverse("process-details", kwargs={"pk": process.id}))


class CSVExportProcessCreate(BaseFileExportProcessCreate):
    file_format = _("CSV")
    supported_campaign_modes = CSV_SUPPORTED_CAMPAIGN_MODES
    process_mode = ProcessMode.CSVExport
    celery_task = csv_export


class XLSXExportProcessCreate(BaseFileExportProcessCreate):
    file_format = _("XLSX")
    supported_campaign_modes = XLSX_SUPPORTED_CAMPAIGN_MODES
    process_mode = ProcessMode.XLSXExport
    celery_task = xlsx_export
