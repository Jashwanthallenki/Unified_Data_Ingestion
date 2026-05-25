from django.urls import path

from . import views

urlpatterns = [
    path("sync/", views.TravelSyncView.as_view(), name="mock-travel-sync"),
]
