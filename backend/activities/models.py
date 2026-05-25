import uuid

from django.conf import settings
from django.db import models

from ingestion.models import IngestionBatch, RawRecord
from tenants.models import Tenant


class NormalizedActivity(models.Model):
    ELIGIBILITY_CHOICES = [
        ("ELIGIBLE", "Eligible"),
        ("NOT_RELEVANT", "Not relevant"),
        ("NEEDS_REVIEW", "Needs review"),
        ("FAILED", "Failed"),
        ("EXCLUDED", "Excluded"),
    ]
    CONFIDENCE_CHOICES = [
        ("HIGH", "High"),
        ("MEDIUM", "Medium"),
        ("LOW", "Low"),
        ("FAILED", "Failed"),
    ]
    REVIEW_STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
        ("CLARIFICATION_REQUESTED", "Clarification requested"),
        ("MARKED_NOT_RELEVANT", "Marked not relevant"),
        ("LOCKED", "Locked"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="activities")
    batch = models.ForeignKey(IngestionBatch, on_delete=models.CASCADE, related_name="activities")
    raw_record = models.ForeignKey(RawRecord, on_delete=models.CASCADE, related_name="activities")

    # Classification
    source_type = models.CharField(max_length=32)
    activity_type = models.CharField(max_length=64)
    activity_subtype = models.CharField(max_length=64, null=True, blank=True)
    scope = models.IntegerField(null=True, blank=True)
    scope_category = models.CharField(max_length=64, null=True, blank=True)

    # Eligibility & method
    eligibility_status = models.CharField(max_length=32, choices=ELIGIBILITY_CHOICES)
    source_hierarchy_rank = models.IntegerField(null=True, blank=True)
    source_of_truth = models.CharField(max_length=64, null=True, blank=True)
    activity_basis = models.CharField(max_length=64, null=True, blank=True)
    calculation_method = models.CharField(max_length=64, null=True, blank=True)
    emission_method = models.CharField(max_length=64, null=True, blank=True)

    # Time
    activity_date = models.DateField(null=True, blank=True)
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)
    calendar_month = models.DateField(null=True, blank=True)
    billing_days = models.IntegerField(null=True, blank=True)

    # Location
    facility_code = models.CharField(max_length=32, null=True, blank=True)
    facility_name = models.CharField(max_length=255, null=True, blank=True)
    facility_country = models.CharField(max_length=64, null=True, blank=True)
    origin = models.CharField(max_length=64, null=True, blank=True)
    destination = models.CharField(max_length=64, null=True, blank=True)

    # Quantity raw + normalized
    quantity = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    unit = models.CharField(max_length=16, null=True, blank=True)
    normalized_quantity = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    normalized_unit = models.CharField(max_length=16, null=True, blank=True)
    usage_per_day = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)

    # Spend
    currency = models.CharField(max_length=8, null=True, blank=True)
    amount = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)

    # Context
    vendor = models.CharField(max_length=255, null=True, blank=True)
    cost_center = models.CharField(max_length=64, null=True, blank=True)
    reference_id = models.CharField(max_length=128, null=True, blank=True)
    event_key = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    parent_event_key = models.CharField(max_length=255, null=True, blank=True)

    # Dedup / reversal / estimate flags
    is_duplicate = models.BooleanField(default=False)
    is_reversal = models.BooleanField(default=False)
    reversal_of = models.CharField(max_length=128, null=True, blank=True)
    is_estimate = models.BooleanField(default=False)
    estimate_reason = models.TextField(null=True, blank=True)
    requires_reconciliation = models.BooleanField(default=False)

    # Emissions
    emission_factor = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    emission_factor_source = models.CharField(max_length=128, null=True, blank=True)
    co2e_kg = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)

    # Quality
    data_quality_score = models.IntegerField(default=0)
    confidence_level = models.CharField(max_length=16, choices=CONFIDENCE_CHOICES, default="LOW")
    method_confidence = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    flags = models.JSONField(default=list)
    field_provenance = models.JSONField(default=dict)
    llm_suggestions = models.JSONField(default=list)  # current unreviewed Groq suggestions
    llm_suggestion_reviewed = models.BooleanField(default=False)

    # Review workflow
    review_status = models.CharField(max_length=32, choices=REVIEW_STATUS_CHOICES, default="PENDING")
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="reviewed_activities",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_comment = models.TextField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="approved_activities",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    locked_snapshot = models.JSONField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "normalized_activity"
        ordering = ["-activity_date", "-created_at"]
        indexes = [
            models.Index(fields=["tenant", "review_status"]),
            models.Index(fields=["tenant", "source_type", "eligibility_status"]),
            models.Index(fields=["batch"]),
            models.Index(fields=["confidence_level"]),
            models.Index(fields=["activity_type", "activity_date"]),
        ]

    def __str__(self):
        q = self.normalized_quantity if self.normalized_quantity is not None else "?"
        u = self.normalized_unit or "?"
        return f"{self.source_type}:{self.activity_type} {self.activity_date} q={q}{u}"

    @property
    def is_locked(self) -> bool:
        return self.locked_at is not None


class ValidationIssue(models.Model):
    SEVERITY_CHOICES = [
        ("ERROR", "Error"),
        ("WARNING", "Warning"),
        ("INFO", "Info"),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="validation_issues")
    activity = models.ForeignKey(NormalizedActivity, on_delete=models.CASCADE, related_name="issues")
    issue_code = models.CharField(max_length=64)
    severity = models.CharField(max_length=8, choices=SEVERITY_CHOICES, default="WARNING")
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "validation_issue"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["activity", "severity"]),
            models.Index(fields=["issue_code"]),
        ]

    def __str__(self):
        return f"{self.issue_code} ({self.severity})"


class ReviewLog(models.Model):
    ACTION_CHOICES = [
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
        ("FLAGGED", "Flagged"),
        ("MARKED_NOT_RELEVANT", "Marked not relevant"),
        ("CLARIFICATION_REQUESTED", "Clarification requested"),
        ("LOCKED", "Locked"),
        ("UNLOCK_REQUESTED", "Unlock requested"),
        ("LLM_SUGGESTION_ACCEPTED", "LLM suggestion accepted"),
        ("LLM_SUGGESTION_REJECTED", "LLM suggestion rejected"),
        ("VALUE_OVERRIDDEN", "Value overridden"),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="review_logs")
    activity = models.ForeignKey(NormalizedActivity, on_delete=models.CASCADE, related_name="review_logs")
    action = models.CharField(max_length=32, choices=ACTION_CHOICES)
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
    )
    comment = models.TextField(null=True, blank=True)
    old_value = models.JSONField(null=True, blank=True)
    new_value = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "review_log"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["activity"]),
            models.Index(fields=["action"]),
        ]

    def __str__(self):
        return f"{self.activity_id} {self.action} @ {self.created_at}"


class GroqSuggestionCache(models.Model):
    """Cache key = raw_record_id + missing_fields_hash."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    raw_record = models.ForeignKey(RawRecord, on_delete=models.CASCADE, related_name="groq_cache")
    missing_fields_hash = models.CharField(max_length=64)
    response_json = models.JSONField()
    model_used = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "groq_suggestion_cache"
        unique_together = [("raw_record", "missing_fields_hash")]
