from django.contrib import admin

from .models import GroqSuggestionCache, NormalizedActivity, ReviewLog, ValidationIssue


class ValidationIssueInline(admin.TabularInline):
    model = ValidationIssue
    extra = 0
    readonly_fields = ("id", "issue_code", "severity", "message", "created_at")
    can_delete = False


class ReviewLogInline(admin.TabularInline):
    model = ReviewLog
    extra = 0
    readonly_fields = ("id", "action", "reviewer", "comment", "old_value", "new_value", "created_at")
    can_delete = False


@admin.register(NormalizedActivity)
class NormalizedActivityAdmin(admin.ModelAdmin):
    list_display = (
        "source_type", "activity_type", "activity_subtype",
        "facility_name", "activity_date",
        "normalized_quantity", "normalized_unit", "co2e_kg",
        "confidence_level", "data_quality_score",
        "eligibility_status", "review_status",
    )
    list_filter = (
        "source_type", "activity_type", "eligibility_status",
        "confidence_level", "review_status", "calculation_method",
        "is_estimate", "is_duplicate", "is_reversal",
    )
    search_fields = ("facility_name", "facility_code", "reference_id", "vendor", "origin", "destination")
    readonly_fields = ("id", "created_at", "updated_at", "locked_at", "locked_snapshot")
    inlines = [ValidationIssueInline, ReviewLogInline]


@admin.register(ValidationIssue)
class ValidationIssueAdmin(admin.ModelAdmin):
    list_display = ("issue_code", "severity", "activity", "created_at")
    list_filter = ("severity", "issue_code")
    search_fields = ("issue_code", "message")


@admin.register(ReviewLog)
class ReviewLogAdmin(admin.ModelAdmin):
    list_display = ("action", "activity", "reviewer", "created_at")
    list_filter = ("action",)
    readonly_fields = ("id", "created_at", "old_value", "new_value")


@admin.register(GroqSuggestionCache)
class GroqSuggestionCacheAdmin(admin.ModelAdmin):
    list_display = ("raw_record", "missing_fields_hash", "model_used", "created_at")
    readonly_fields = ("id", "created_at", "response_json")
