from django.urls import path

from . import views

urlpatterns = [
    path("sync/", views.TravelSyncView.as_view(), name="mock-travel-sync"),
    path("upload/", views.TravelUploadView.as_view(), name="mock-travel-upload"),
    path("uploads/", views.TravelUploadInspectView.as_view(), name="mock-travel-uploads"),
]
