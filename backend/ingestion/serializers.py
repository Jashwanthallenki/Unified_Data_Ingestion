from rest_framework import serializers

from .models import IngestionBatch, RawRecord


class IngestionBatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = IngestionBatch
        fields = [
            "id", "tenant", "source_type", "ingestion_method",
            "original_filename", "api_sync_range_start", "api_sync_range_end",
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


class RawRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = RawRecord
        fields = [
            "id", "batch", "source_type", "row_number",
            "raw_payload", "parse_status",
            "eligibility_status", "exclusion_reason",
            "error_message", "created_at",
        ]
        read_only_fields = fields


class ExclusionRowSerializer(serializers.ModelSerializer):
    class Meta:
        model = RawRecord
        fields = ["id", "row_number", "exclusion_reason", "parse_status", "eligibility_status", "raw_payload"]
        read_only_fields = fields
