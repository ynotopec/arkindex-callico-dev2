from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http.response import Http404
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.generic import CreateView

from callico.process.arkindex.exports import ARKINDEX_PUBLISH_METHODS
from callico.process.arkindex.forms import ArkindexExportProcessCreateForm, ArkindexImportProcessCreateForm
from callico.process.arkindex.tasks import arkindex_export, arkindex_import
from callico.process.models import ProcessMode
from callico.projects.mixins import ProjectACLMixin
from callico.projects.models import Campaign, CampaignMode, CampaignState, Class, Project, ProviderType, Type


class ArkindexImportProcessCreate(LoginRequiredMixin, ProjectACLMixin, CreateView):
    form_class = ArkindexImportProcessCreateForm
    template_name = "arkindex/arkindex_import_process_create.html"

    def get_project(self):
        try:
            project = Project.objects.select_related("provider").get(id=self.kwargs["pk"])
        except Project.DoesNotExist:
            raise Http404(_("No project matching this ID exists"))

        # Raise a forbidden error now if user shouldn't access this page
        if not self.has_manager_access(project):
            raise PermissionDenied(_("You don't have the required rights to create a process on this project"))

        if not project.provider or project.provider.type != ProviderType.Arkindex:
            raise Http404(
                _("You can't create an Arkindex import process on a project that isn't linked to an Arkindex provider")
            )

        return project

    def get_form_kwargs(self):
        # Retrieving the project now to raise a forbidden error if user shouldn't access this page
        self.project = self.get_project()

        kwargs = super().get_form_kwargs()
        kwargs["ml_classes"] = (
            Class.objects.filter(project=self.project, provider=self.project.provider)
            .order_by("name")
            .values_list("name", flat=True)
        )
        kwargs["types"] = (
            Type.objects.filter(project=self.project, provider=self.project.provider)
            .order_by("name")
            .values("name", "provider_object_id")
        )
        kwargs["worker_runs"] = self.project.provider_extra_information.get("worker_runs", [])
        return kwargs

    def form_valid(self, form):
        form.instance.mode = ProcessMode.ArkindexImport
        form.instance.project = self.project
        form.instance.creator = self.request.user
        form.instance.configuration = {
            "arkindex_provider": str(self.project.provider.id),
            "project_id": str(self.project.id),
            "types": form.cleaned_data["types"],
            "class_name": form.cleaned_data["ml_class"],
            "transcriptions": form.cleaned_data["transcriptions"],
            "entities": form.cleaned_data["entities"],
            "elements_worker_run": form.cleaned_data["elements_worker_run"],
            "metadata": form.cleaned_data["metadata"],
            "corpus": self.project.provider_object_id,
            "element": str(form.cleaned_data["element"]) if form.cleaned_data["element"] else None,
            "dataset": str(form.cleaned_data["dataset"]) if form.cleaned_data["dataset"] else None,
            "dataset_sets": form.cleaned_data["dataset_sets"],
        }

        arkindex_import.apply_async(kwargs=form.instance.configuration, task_id=str(form.instance.id))

        messages.add_message(
            self.request, messages.SUCCESS, _("The process to import elements from Arkindex has been started.")
        )

        return super().form_valid(form)

    def get_success_url(self):
        return reverse("process-details", kwargs={"pk": self.object.id})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["project"] = self.project
        return context


class ArkindexExportProcessCreate(LoginRequiredMixin, ProjectACLMixin, CreateView):
    template_name = "arkindex/arkindex_export_process_create.html"
    form_class = ArkindexExportProcessCreateForm

    def get_campaign(self):
        try:
            campaign = Campaign.objects.select_related("project__provider").get(id=self.kwargs["pk"])
        except Campaign.DoesNotExist:
            raise Http404(_("No campaign matching this ID exists"))

        # Raise a forbidden error now if the user shouldn't be able to access this page
        if not self.has_manager_access(campaign.project):
            raise PermissionDenied(
                _("You don't have access to this campaign and can't export its annotations to Arkindex")
            )

        if campaign.state == CampaignState.Archived:
            raise PermissionDenied(
                _("You cannot export annotations to Arkindex from a campaign marked as %(state)s")
                % {"state": campaign.get_state_display()}
            )

        if campaign.mode not in ARKINDEX_PUBLISH_METHODS:
            raise Http404(
                _("You cannot export annotations to Arkindex for a campaign of type %(mode)s")
                % {"mode": campaign.get_mode_display()}
            )

        if not campaign.project.provider or campaign.project.provider.type != ProviderType.Arkindex:
            raise Http404(
                _("You can't create an Arkindex export process on a project that isn't linked to an Arkindex provider")
            )

        if not campaign.project.provider.extra_information.get("worker_run_publication"):
            raise Http404(
                _(
                    "You can't create an Arkindex export process on a project for which the Arkindex provider doesn't have a worker run ID for publication in its extra information field"
                )
            )

        return campaign

    def get_form_kwargs(self):
        self.campaign = self.get_campaign()

        kwargs = super().get_form_kwargs()
        kwargs["campaign"] = self.campaign
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["campaign"] = self.campaign
        return context

    def form_valid(self, form):
        form.instance.mode = ProcessMode.ArkindexExport
        form.instance.creator = self.request.user
        form.instance.project = self.campaign.project
        form.instance.configuration = {
            "arkindex_provider": str(self.campaign.project.provider.id),
            "campaign": str(self.campaign.id),
            "corpus": str(self.campaign.project.provider_object_id),
            "worker_run": str(self.campaign.project.provider.extra_information["worker_run_publication"]),
            "exported_states": form.cleaned_data["exported_states"],
            "force_republication": form.cleaned_data.get("force_republication", False),
            "use_raw_publication": form.cleaned_data.get("use_raw_publication", False),
        }

        if self.campaign.mode == CampaignMode.EntityForm:
            form.instance.configuration["entities_order"] = form.cleaned_data.get("entities_order", [])
            form.instance.configuration["concatenation_parent_type"] = form.cleaned_data.get(
                "concatenation_parent_type"
            )

        arkindex_export.apply_async(kwargs=form.instance.configuration, task_id=str(form.instance.id))

        messages.add_message(
            self.request, messages.SUCCESS, _("The process to export annotations to Arkindex has been started.")
        )

        return super().form_valid(form)

    def get_success_url(self):
        return reverse("process-details", kwargs={"pk": self.object.id})
