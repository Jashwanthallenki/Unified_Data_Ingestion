from rest_framework import serializers

from .models import NormalizedActivity, ReviewLog, ValidationIssue


class ValidationIssueSerializer(serializers.ModelSerializer):
    class Meta:
        model = ValidationIssue
        fields = ["id", "issue_code", "severity", "message", "created_at"]
        read_only_fields = fields


class ReviewLogSerializer(serializers.ModelSerializer):
    reviewer_username = serializers.SerializerMethodField()

    class Meta:
        model = ReviewLog
        fields = ["id", "action", "reviewer", "reviewer_username", "comment",
                  "old_value", "new_value", "created_at"]
        read_only_fields = fields

    def get_reviewer_username(self, obj) -> str | None:
        return obj.reviewer.username if obj.reviewer_id else None


_BASE_FIELDS = [
    "id", "batch", "source_type", "activity_type", "activity_subtype",
    "scope", "scope_category",
    "eligibility_status", "review_status",
    "activity_basis", "calculation_method", "emission_method",
    "source_hierarchy_rank", "source_of_truth",
    "activity_date", "period_start", "period_end", "calendar_month", "billing_days",
    "facility_code", "facility_name", "facility_country",
    "origin", "destination",
    "quantity", "unit", "normalized_quantity", "normalized_unit",
    "usage_per_day",
    "currency", "amount",
    "vendor", "cost_center", "reference_id",
    "is_duplicate", "is_reversal", "is_estimate", "requires_reconciliation",
    "emission_factor", "emission_factor_source", "co2e_kg",
    "data_quality_score", "confidence_level", "method_confidence",
    "flags",
    "llm_suggestion_reviewed",
    "approved_at", "locked_at",
    "created_at",
]


class NormalizedActivityListSerializer(serializers.ModelSerializer):
    """Compact representation for the review table."""

    issue_count = serializers.SerializerMethodField()

    class Meta:
        model = NormalizedActivity
        fields = _BASE_FIELDS + ["issue_count"]
        read_only_fields = fields

    def get_issue_count(self, obj) -> int:
        # Prefer the annotation if present (set by the list view), else query.
        annotated = getattr(obj, "issue_count", None)
        if isinstance(annotated, int):
            return annotated
        return obj.issues.count()


class NormalizedActivityDetailSerializer(serializers.ModelSerializer):
    issues = ValidationIssueSerializer(many=True, read_only=True)
    review_logs = ReviewLogSerializer(many=True, read_only=True)
    raw_payload = serializers.SerializerMethodField()
    issue_count = serializers.SerializerMethodField()

    class Meta:
        model = NormalizedActivity
        fields = _BASE_FIELDS + [
            "field_provenance", "llm_suggestions", "review_comment",
            "reviewed_by", "reviewed_at", "approved_by", "locked_snapshot",
            "issues", "review_logs", "raw_payload", "issue_count",
        ]
        read_only_fields = fields

    def get_raw_payload(self, obj):
        return obj.raw_record.raw_payload if obj.raw_record_id else None

    def get_issue_count(self, obj) -> int:
        return obj.issues.count()
