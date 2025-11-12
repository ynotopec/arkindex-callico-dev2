from celery import shared_task

from callico.process.arkindex.exports import ArkindexExport
from callico.process.arkindex.imports import ArkindexFetchExtraInfo, ArkindexImport
from callico.process.models import Process


@shared_task(bind=True)
def arkindex_fetch_extra_info(self, **configuration):
    process = Process.objects.get(id=self.request.id)

    fetch_extra_info_process = ArkindexFetchExtraInfo(
        process, configuration["arkindex_provider"], configuration["project_id"]
    )
    fetch_extra_info_process.run()


@shared_task(bind=True)
def arkindex_import(self, **configuration):
    process = Process.objects.get(id=self.request.id)

    import_process = ArkindexImport.from_configuration(process, configuration)
    import_process.run(
        element_id=configuration["element"], dataset_id=configuration["dataset"], corpus_id=configuration["corpus"]
    )


@shared_task(bind=True)
def arkindex_export(self, **configuration):
    process = Process.objects.get(id=self.request.id)

    export_process = ArkindexExport.from_configuration(process, configuration)
    export_process.run()
