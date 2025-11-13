from django.urls import path

from callico.process.arkindex.views import ArkindexExportProcessCreate, ArkindexImportProcessCreate
from callico.process.views import CSVExportProcessCreate, ProcessDetails, ProcessList, XLSXExportProcessCreate

urlpatterns = [
    path("project/<uuid:pk>/", ProcessList.as_view(), name="processes"),
    path("<uuid:pk>/details/", ProcessDetails.as_view(), name="process-details"),
    path("project/<uuid:pk>/import-arkindex/", ArkindexImportProcessCreate.as_view(), name="arkindex-import-create"),
    path("campaign/<uuid:pk>/csv-export/", CSVExportProcessCreate.as_view(), name="csv-export-create"),
    path("campaign/<uuid:pk>/xlsx-export/", XLSXExportProcessCreate.as_view(), name="xlsx-export-create"),
    path("campaign/<uuid:pk>/arkindex-export/", ArkindexExportProcessCreate.as_view(), name="arkindex-export-create"),
]
