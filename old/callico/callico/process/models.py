import json
import logging
import uuid
from datetime import datetime, timezone

from django.db import models
from django.utils.translation import gettext_lazy as _

from callico.base.celery import app

logger = logging.getLogger(__name__)

UNTRACKED = ["callico.users.tasks.send_email", "callico.users.tasks.send_daily_statistics"]


class ProcessMode(models.TextChoices):
    ArkindexImport = "arkindex_import", _("Arkindex import")
    ArkindexExport = "arkindex_export", _("Arkindex export")
    CSVExport = "csv_export", _("CSV export")
    XLSXExport = "xlsx_export", _("XLSX export")


class ProcessState(models.TextChoices):
    Created = "created", _("Created")
    Running = "running", _("Running")
    Completed = "completed", _("Completed")
    Error = "error", _("Error")


PROCESS_FINAL_STATES = [ProcessState.Completed, ProcessState.Error]


class Process(models.Model):
    # Will be manually attributed to the Celery task through apply_async(task_id=<id>)
    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    name = models.CharField(max_length=512, verbose_name=_("Name"))
    mode = models.CharField(max_length=32, choices=ProcessMode, verbose_name=_("Mode"))
    state = models.CharField(max_length=32, choices=ProcessState, default=ProcessState.Created, verbose_name=_("State"))
    configuration = models.JSONField(blank=True, default=dict, verbose_name=_("Configuration"))
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="processes",
        verbose_name=_("Project"),
    )
    creator = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="processes",
        verbose_name=_("Creator"),
    )
    logs = models.TextField(blank=True, default="", verbose_name=_("Logs"))

    created = models.DateTimeField(auto_now_add=True, verbose_name=_("Created"))
    started = models.DateTimeField(null=True, blank=True, verbose_name=_("Started"))
    ended = models.DateTimeField(null=True, blank=True, verbose_name=_("Ended"))

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _("Process")
        verbose_name_plural = _("Processes")

    @property
    def parsed_logs(self):
        splitted_logs = self.logs.split("\n")

        parsed_logs = []
        for str_obj in splitted_logs:
            try:
                parsed_logs.append(json.loads(str_obj))
            except Exception:
                continue

        return parsed_logs

    def add_log(self, log, level):
        if not logger.isEnabledFor(level):
            return

        ndjson_log = json.dumps(
            {"content": log, "level": level, "date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")}
        )
        self.logs += f"{ndjson_log}\n"
        self.save()

        logger.log(level, log)

    def start(self):
        self.started = datetime.now(timezone.utc)
        self.state = ProcessState.Running
        self.save()

    def end(self, state=ProcessState.Completed):
        self.ended = datetime.now(timezone.utc)
        self.state = state
        self.save()

    def error(self, error):
        self.end(state=ProcessState.Error)
        self.add_log(f"An error occurred during the process {self.id}: {error}", logging.ERROR)

    def stop(self, user):
        # We don't need to stop a process that has already ended
        if self.state in PROCESS_FINAL_STATES:
            return

        app.control.revoke(str(self.id), terminate=True)
        self.end(state=ProcessState.Error)
        self.add_log(f"The process {self.id} was stopped by the user {user}", logging.ERROR)
