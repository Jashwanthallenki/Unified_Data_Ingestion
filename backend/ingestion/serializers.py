from django.db.models import Q
from rest_framework import serializers

from activities.models import NormalizedActivity

from .models import IngestionBatch, RawRecord


class IngestionBatchSerializer(serializers.ModelSerializer):
    duplicate_rows_count = serializers.SerializerMethodField()
    reconciliation_needed_count = serializers.SerializerMethodField()

    class Meta:
        model = IngestionBatch
        fields = [
            "id", "tenant", "source_type", "ingestion_method",
            "original_filename", "api_sync_range_start", "api_sync_range_end",
            "file_hash", "content_hash", "sync_key",
            "is_duplicate_file", "duplicate_of_batch",
            "duplicate_rows_count", "reconciliation_needed_count",
            "uploaded_at", "status",
            "total_rows", "raw_rows_stored",
            "eligible_rows", "excluded_rows", "not_relevant_rows",
            "failed_rows", "successful_rows",
            "flagged_rows", "suspicious_rows", "low_confidence_rows", "llm_suggested_rows",
            "pending_rows", "approved_rows", "rejected_rows", "locked_rows",
            "plant_lookup_version", "material_lookup_version", "unit_mapping_version",
            "meter_mapping_version", "ef_version",
            "notes", "error_message",
            "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_duplicate_rows_count(self, obj) -> int:
        return obj.raw_records.filter(is_duplicate_row=True).count()

    def get_reconciliation_needed_count(self, obj) -> int:
        return NormalizedActivity.objects.filter(
            batch=obj,
        ).filter(
            Q(is_duplicate=True) | Q(requires_reconciliation=True)
        ).count()


class RawRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = RawRecord
        fields = [
            "id", "batch", "source_type", "row_number",
            "raw_payload", "parse_status",
            "row_hash", "source_event_key", "is_duplicate_row", "duplicate_of_raw_record",
            "eligibility_status", "exclusion_reason",
            "error_message", "created_at",
        ]
        read_only_fields = fields


class ExclusionRowSerializer(serializers.ModelSerializer):
    class Meta:
        model = RawRecord
        fields = ["id", "row_number", "exclusion_reason", "parse_status", "eligibility_status", "raw_payload"]
        read_only_fields = fields


class DuplicateRawRecordSerializer(serializers.ModelSerializer):
    duplicate_of_raw_record_row = serializers.SerializerMethodField()

    class Meta:
        model = RawRecord
        fields = [
            "id", "batch", "source_type", "row_number", "row_hash", "source_event_key",
            "is_duplicate_row", "duplicate_of_raw_record", "duplicate_of_raw_record_row",
            "raw_payload", "parse_status", "eligibility_status", "exclusion_reason",
            "error_message", "created_at",
        ]
        read_only_fields = fields

    def get_duplicate_of_raw_record_row(self, obj) -> int | None:
        return obj.duplicate_of_raw_record.row_number if obj.duplicate_of_raw_record_id else None
