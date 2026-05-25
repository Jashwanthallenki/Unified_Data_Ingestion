from django.urls import path

from . import views

urlpatterns = [
    path("sap/upload/", views.SapUploadView.as_view(), name="ingestion-sap-upload"),
    path("utility/upload/", views.UtilityUploadView.as_view(), name="ingestion-utility-upload"),
    path("travel-sync/", views.TravelSyncView.as_view(), name="ingestion-travel-sync"),
    path("batches/", views.BatchListView.as_view(), name="ingestion-batches"),
    path("batches/<uuid:batch_id>/", views.BatchDetailView.as_view(), name="ingestion-batch-detail"),
    path("batches/<uuid:batch_id>/raw-records/", views.BatchRawRecordsView.as_view(), name="ingestion-batch-raw"),
    path("batches/<uuid:batch_id>/exclusions/", views.BatchExclusionsView.as_view(), name="ingestion-batch-exclusions"),
]
