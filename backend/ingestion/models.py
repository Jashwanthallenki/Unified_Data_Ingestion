import uuid

from django.db import models

from tenants.models import Tenant


class IngestionBatch(models.Model):
    SOURCE_CHOICES = [
        ("sap", "SAP"),
        ("utility", "Utility"),
        ("travel", "Travel"),
    ]
    METHOD_CHOICES = [
        ("FILE_UPLOAD", "File upload"),
        ("API_PULL", "API pull"),
    ]
    STATUS_CHOICES = [
        ("PROCESSING", "Processing"),
        ("COMPLETE", "Complete"),
        ("FAILED", "Failed"),
        ("PARTIAL", "Partial"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="batches")
    source_type = models.CharField(max_length=32, choices=SOURCE_CHOICES)
    ingestion_method = models.CharField(max_length=32, choices=METHOD_CHOICES)
    original_filename = models.CharField(max_length=255, null=True, blank=True)
    api_sync_range_start = models.DateField(null=True, blank=True)
    api_sync_range_end = models.DateField(null=True, blank=True)
    file_hash = models.CharField(max_length=128, null=True, blank=True, db_index=True)
    content_hash = models.CharField(max_length=128, null=True, blank=True, db_index=True)
    sync_key = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    is_duplicate_file = models.BooleanField(default=False)
    duplicate_of_batch = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="duplicate_batches",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="PROCESSING")

    # Counts populated by the pipeline at each stage.
    total_rows = models.IntegerField(default=0)
    raw_rows_stored = models.IntegerField(default=0)
    eligible_rows = models.IntegerField(default=0)
    excluded_rows = models.IntegerField(default=0)
    not_relevant_rows = models.IntegerField(default=0)
    failed_rows = models.IntegerField(default=0)
    successful_rows = models.IntegerField(default=0)
    flagged_rows = models.IntegerField(default=0)
    suspicious_rows = models.IntegerField(default=0)
    low_confidence_rows = models.IntegerField(default=0)
    llm_suggested_rows = models.IntegerField(default=0)

    pending_rows = models.IntegerField(default=0)
    approved_rows = models.IntegerField(default=0)
    rejected_rows = models.IntegerField(default=0)
    locked_rows = models.IntegerField(default=0)

    # Lookup versions in effect at ingestion (snapshot for audit).
    plant_lookup_version = models.CharField(max_length=32, null=True, blank=True)
    material_lookup_version = models.CharField(max_length=32, null=True, blank=True)
    unit_mapping_version = models.CharField(max_length=32, null=True, blank=True)
    meter_mapping_version = models.CharField(max_length=32, null=True, blank=True)
    ef_version = models.CharField(max_length=32, null=True, blank=True)

    notes = models.TextField(blank=True)
    error_message = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "ingestion_batch"
        ordering = ["-uploaded_at"]
        indexes = [
            models.Index(fields=["tenant", "-uploaded_at"]),
            models.Index(fields=["tenant", "source_type"]),
        ]

    def __str__(self):
        return f"{self.source_type} batch {self.id} ({self.status})"


class RawRecord(models.Model):
    PARSE_STATUS_CHOICES = [
        ("PARSED", "Parsed"),
        ("FAILED", "Failed"),
        ("EXCLUDED", "Excluded"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="raw_records")
    batch = models.ForeignKey(IngestionBatch, on_delete=models.CASCADE, related_name="raw_records")
    source_type = models.CharField(max_length=32)
    row_number = models.IntegerField()
    raw_payload = models.JSONField()
    row_hash = models.CharField(max_length=128, default="", blank=True, db_index=True)
    source_event_key = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    is_duplicate_row = models.BooleanField(default=False)
    duplicate_of_raw_record = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="duplicate_raw_rows",
    )
    parse_status = models.CharField(max_length=16, choices=PARSE_STATUS_CHOICES, default="PARSED")
    eligibility_status = models.CharField(max_length=32, null=True, blank=True)
    exclusion_reason = models.CharField(max_length=128, null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "raw_record"
        ordering = ["batch", "row_number"]
        indexes = [
            models.Index(fields=["batch", "parse_status"]),
            models.Index(fields=["batch", "eligibility_status"]),
        ]

    def __str__(self):
        return f"{self.batch_id} row {self.row_number} {self.parse_status}"
