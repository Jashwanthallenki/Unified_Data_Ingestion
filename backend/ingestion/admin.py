from django.contrib import admin

from .models import IngestionBatch, RawRecord


@admin.register(IngestionBatch)
class IngestionBatchAdmin(admin.ModelAdmin):
    list_display = (
        "id", "source_type", "ingestion_method", "status",
        "total_rows", "eligible_rows", "excluded_rows", "low_confidence_rows",
        "uploaded_at",
    )
    list_filter = ("source_type", "status", "ingestion_method")
    readonly_fields = ("id", "uploaded_at", "created_at", "updated_at")
    search_fields = ("original_filename", "id")
    fieldsets = (
        (None, {"fields": ("id", "tenant", "source_type", "ingestion_method", "status")}),
        ("Source", {"fields": ("original_filename", "api_sync_range_start", "api_sync_range_end")}),
        (
            "Counts",
            {
                "fields": (
                    "total_rows", "raw_rows_stored",
                    "eligible_rows", "excluded_rows", "not_relevant_rows",
                    "failed_rows", "successful_rows",
                    "flagged_rows", "suspicious_rows", "low_confidence_rows", "llm_suggested_rows",
                    "pending_rows", "approved_rows", "rejected_rows", "locked_rows",
                )
            },
        ),
        (
            "Lookup versions (snapshot)",
            {
                "fields": (
                    "plant_lookup_version", "material_lookup_version",
                    "unit_mapping_version", "meter_mapping_version", "ef_version",
                )
            },
        ),
        ("Diagnostics", {"fields": ("notes", "error_message", "uploaded_at", "created_at", "updated_at")}),
    )


@admin.register(RawRecord)
class RawRecordAdmin(admin.ModelAdmin):
    list_display = ("batch", "row_number", "source_type", "parse_status", "eligibility_status", "exclusion_reason")
    list_filter = ("source_type", "parse_status", "eligibility_status")
    search_fields = ("exclusion_reason", "error_message")
    readonly_fields = ("id", "created_at", "raw_payload")
