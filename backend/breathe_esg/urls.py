from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from django.views.generic import TemplateView


def healthz(_request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/healthz/", healthz, name="healthz"),
    path("api/ingestion/", include("ingestion.urls")),
    path("api/review/", include("activities.urls")),
    path("api/mock-travel/", include("mock_travel.urls")),
    # Catch-all serves the React SPA (or the placeholder if frontend not built).
    path("", TemplateView.as_view(template_name="index.html"), name="spa-root"),
    path("<path:_unused>", TemplateView.as_view(template_name="index.html"), name="spa-catchall"),
]
