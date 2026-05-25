from django.urls import path

from . import views

urlpatterns = [
    path("activities/", views.ActivityListView.as_view(), name="review-activities"),
    path("activities/<uuid:activity_id>/", views.ActivityDetailView.as_view(), name="review-activity-detail"),
    path("activities/<uuid:activity_id>/approve/", views.ActivityApproveView.as_view(), name="review-approve"),
    path("activities/<uuid:activity_id>/reject/", views.ActivityRejectView.as_view(), name="review-reject"),
    path("activities/<uuid:activity_id>/mark-not-relevant/", views.ActivityMarkNotRelevantView.as_view(), name="review-not-relevant"),
    path("activities/<uuid:activity_id>/request-clarification/", views.ActivityRequestClarificationView.as_view(), name="review-clarify"),
    path("activities/<uuid:activity_id>/override/", views.ActivityOverrideView.as_view(), name="review-override"),
    path("activities/<uuid:activity_id>/lock/", views.ActivityLockView.as_view(), name="review-lock"),
    path("activities/<uuid:activity_id>/groq-suggest/", views.ActivityGroqSuggestView.as_view(), name="review-groq-suggest"),
    path("activities/<uuid:activity_id>/accept-llm-suggestion/", views.ActivityAcceptLlmView.as_view(), name="review-llm-accept"),
    path("activities/<uuid:activity_id>/reject-llm-suggestion/", views.ActivityRejectLlmView.as_view(), name="review-llm-reject"),
    path("summary/", views.ReviewSummaryView.as_view(), name="review-summary"),
]
