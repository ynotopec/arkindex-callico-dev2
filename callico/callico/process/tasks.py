import csv
import logging
import os

import xlsxwriter
from celery import shared_task, states
from celery.signals import task_postrun, task_prerun
from django.core import files
from django.core.files.temp import NamedTemporaryFile

from callico.annotations.models import TaskState, TaskUser
from callico.process.exports import create_table_header, create_table_row
from callico.process.models import PROCESS_FINAL_STATES, UNTRACKED, Process
from callico.projects.models import CSV_SUPPORTED_CAMPAIGN_MODES, XLSX_SUPPORTED_CAMPAIGN_MODES, Campaign

CHUNK_SIZE = 5000


@task_prerun.connect
def start_process(task_id, task, *args, **kwargs):
    if task.name in UNTRACKED:
        return

    process = Process.objects.get(id=task_id)
    process.start()


@task_postrun.connect
def end_process(task_id, task, *args, **kwargs):
    if task.name in UNTRACKED:
        return

    process = Process.objects.get(id=task_id)

    if process.state not in PROCESS_FINAL_STATES:
        if kwargs.get("state") == states.SUCCESS:
            process.end()
        elif kwargs.get("state") == states.FAILURE:
            process.error(str(kwargs.get("retval", "")))


@shared_task(bind=True)
def csv_export(self, **configuration):
    process = Process.objects.get(id=self.request.id)

    campaign = Campaign.objects.get(id=configuration["campaign_id"])
    assert campaign.mode in CSV_SUPPORTED_CAMPAIGN_MODES, "CSV export for this campaign mode is not yet supported"

    try:
        # Creating a temporary file to save the results
        with NamedTemporaryFile(suffix=".csv", delete=False, mode="w") as csv_file:
            writer = csv.writer(csv_file)

            # Composing the header of the CSV
            header, extra_data = create_table_header(campaign)
            writer.writerow(header)

            # Adding rows containing the campaign results to the CSV
            exported = False
            for user_task in (
                TaskUser.objects.select_related("user")
                .filter(
                    task__campaign=campaign,
                    state__in=[TaskState.Annotated, TaskState.Validated],
                    annotations__isnull=False,
                    is_preview=False,
                )
                .distinct()
                .iterator(chunk_size=CHUNK_SIZE)
            ):
                try:
                    values = create_table_row(process, campaign, user_task, extra_data)
                    writer.writerow(values)
                except Exception as e:
                    process.add_log(
                        f"Failed to export the last annotation on user task {user_task.id} in the CSV: {e}",
                        logging.ERROR,
                    )
                else:
                    # If at least one row is created, no need to mark the export as a failure
                    exported = True

            if not exported:
                raise Exception("No valid results to be exported were found for this campaign, no file will be created")

        # Cleaning a potential previous export
        if campaign.csv_export:
            campaign.csv_export.delete()

        with open(csv_file.name, "rb") as csv_file_bytes:
            # Saving the temporary CSV file on the campaign
            export_name = f"export-{str(campaign.id)[:8]}.csv"
            campaign.csv_export = files.File(csv_file_bytes, name=export_name)
            campaign.save()
    finally:
        os.remove(csv_file.name)


@shared_task(bind=True)
def xlsx_export(self, **configuration):
    process = Process.objects.get(id=self.request.id)

    campaign = Campaign.objects.get(id=configuration["campaign_id"])
    assert campaign.mode in XLSX_SUPPORTED_CAMPAIGN_MODES, "XLSX export for this campaign mode is not yet supported"

    try:
        export_name = f"export-{str(campaign.id)[:8]}.xlsx"
        tmp_export_name = f"tmp-{export_name}"
        with xlsxwriter.Workbook(
            tmp_export_name, {"default_date_format": "YYYY-MM-DD HH:mm:ss", "remove_timezone": True}
        ) as workbook:
            worksheet = workbook.add_worksheet()
            bold = workbook.add_format({"bold": 1})

            # Composing the header of the XLSX
            header, extra_data = create_table_header(campaign)
            for i, col_name in enumerate(header):
                worksheet.write(0, i, col_name, bold)

            # Adding rows containing the campaign results to the XLSX
            exported = False
            row = 1
            for user_task in (
                TaskUser.objects.select_related("user")
                .filter(
                    task__campaign=campaign,
                    state__in=[TaskState.Annotated, TaskState.Validated],
                    annotations__isnull=False,
                    is_preview=False,
                )
                .distinct()
                .iterator(chunk_size=CHUNK_SIZE)
            ):
                try:
                    values = create_table_row(process, campaign, user_task, extra_data)
                    for i, value in enumerate(values):
                        worksheet.write(row, i, value)

                    row += 1
                except Exception as e:
                    process.add_log(
                        f"Failed to export the last annotation on user task {user_task.id} in the XLSX: {e}",
                        logging.ERROR,
                    )
                else:
                    # If at least one row is created, no need to mark the export as a failure
                    exported = True

            if not exported:
                raise Exception("No valid results to be exported were found for this campaign, no file will be created")

            # Resize columns width for a better user experience
            worksheet.autofit()

        # Cleaning a potential previous export
        if campaign.xlsx_export:
            campaign.xlsx_export.delete()

        with open(tmp_export_name, "rb") as xlsx_file_bytes:
            # Saving the temporary XLSX file on the campaign
            campaign.xlsx_export = files.File(xlsx_file_bytes, name=export_name)
            campaign.save()
    finally:
        os.remove(tmp_export_name)
