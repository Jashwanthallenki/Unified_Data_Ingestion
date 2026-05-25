import uuid

from django.db import models

from tenants.models import Tenant


class PlantLookup(models.Model):
    """SAP plant code → facility (tenant-scoped)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="plants")
    plant_code = models.CharField(max_length=32)
    facility_name = models.CharField(max_length=255)
    facility_country = models.CharField(max_length=64, blank=True)
    region = models.CharField(max_length=64, blank=True)
    version = models.CharField(max_length=32, default="v1")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "plant_lookup"
        unique_together = [("tenant", "plant_code", "version")]
        indexes = [models.Index(fields=["tenant", "plant_code"])]

    def __str__(self):
        return f"{self.plant_code} → {self.facility_name}"


class MaterialLookup(models.Model):
    """SAP material code → fuel type / density / default unit (tenant-scoped)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="materials")
    material_code = models.CharField(max_length=64)
    description = models.CharField(max_length=255)
    fuel_type = models.CharField(max_length=64, blank=True)
    default_unit = models.CharField(max_length=16, blank=True)
    density_kg_per_l = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    version = models.CharField(max_length=32, default="v1")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "material_lookup"
        unique_together = [("tenant", "material_code", "version")]
        indexes = [models.Index(fields=["tenant", "material_code"])]

    def __str__(self):
        return f"{self.material_code} {self.description}"


class UnitMapping(models.Model):
    """Source unit code → normalized unit + conversion factor.

    Tenant can be NULL for global default mappings (L → litres, KG → kg, ...).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="unit_mappings", null=True, blank=True
    )
    source_unit = models.CharField(max_length=16)
    normalized_unit = models.CharField(max_length=16)
    conversion_factor = models.DecimalField(max_digits=18, decimal_places=6, default=1)
    note = models.CharField(max_length=255, blank=True)
    version = models.CharField(max_length=32, default="v1")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "unit_mapping"
        unique_together = [("tenant", "source_unit", "version")]
        indexes = [models.Index(fields=["source_unit"])]

    def __str__(self):
        return f"{self.source_unit} → {self.normalized_unit} (×{self.conversion_factor})"


class MovementTypeMapping(models.Model):
    """SAP movement-type semantics — global, not tenant-scoped."""

    ESG_RELEVANCE_CHOICES = [
        ("CONSUMPTION", "Consumption"),
        ("PURCHASE", "Purchase / receipt"),
        ("TRANSFER", "Transfer"),
        ("REVERSAL", "Reversal / return"),
        ("SCRAP", "Scrapping / write-off"),
        ("ADJUSTMENT", "Inventory adjustment"),
        ("UNKNOWN", "Unknown"),
    ]
    DEFAULT_ACTION_CHOICES = [
        ("COUNT_AS_CONSUMPTION", "Count as consumption"),
        ("COUNT_AS_PURCHASE", "Count as purchase"),
        ("FLAG_TRANSFER", "Flag as transfer (exclude from emissions)"),
        ("FLAG_REVERSAL", "Flag as reversal (link & net)"),
        ("IGNORE_NON_RELEVANT", "Ignore (not ESG-relevant)"),
        ("NEEDS_ANALYST_REVIEW", "Needs analyst review"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    movement_type = models.CharField(max_length=8, unique=True)
    description = models.CharField(max_length=255)
    source_meaning = models.CharField(max_length=255, blank=True)
    esg_relevance = models.CharField(max_length=32, choices=ESG_RELEVANCE_CHOICES)
    activity_interpretation = models.CharField(max_length=64, blank=True)
    default_action = models.CharField(max_length=32, choices=DEFAULT_ACTION_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "movement_type_mapping"
        ordering = ["movement_type"]

    def __str__(self):
        return f"{self.movement_type} {self.description}"


class CostCenterLookup(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="cost_centers")
    cost_center_code = models.CharField(max_length=32)
    description = models.CharField(max_length=255, blank=True)
    business_unit = models.CharField(max_length=64, blank=True)
    region = models.CharField(max_length=64, blank=True)
    version = models.CharField(max_length=32, default="v1")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "cost_center_lookup"
        unique_together = [("tenant", "cost_center_code", "version")]

    def __str__(self):
        return f"{self.cost_center_code} {self.description}"


class MeterFacilityLookup(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="meters")
    provider = models.CharField(max_length=128)
    account_number = models.CharField(max_length=64)
    meter_number = models.CharField(max_length=64)
    service_address = models.CharField(max_length=255, blank=True)
    facility_code = models.CharField(max_length=32)
    facility_name = models.CharField(max_length=255)
    facility_country = models.CharField(max_length=64, blank=True)
    version = models.CharField(max_length=32, default="v1")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "meter_facility_lookup"
        unique_together = [
            ("tenant", "provider", "account_number", "meter_number", "version")
        ]
        indexes = [models.Index(fields=["tenant", "meter_number"])]

    def __str__(self):
        return f"{self.provider}/{self.account_number}/{self.meter_number} → {self.facility_name}"


class AirportLookup(models.Model):
    """IATA airport reference — global."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    iata_code = models.CharField(max_length=4, unique=True)
    name = models.CharField(max_length=255)
    city = models.CharField(max_length=128, blank=True)
    country = models.CharField(max_length=64, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "airport_lookup"
        ordering = ["iata_code"]

    def __str__(self):
        return f"{self.iata_code} {self.name}"


class CityCodeLookup(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    city_code = models.CharField(max_length=8, unique=True)
    city_name = models.CharField(max_length=128)
    country = models.CharField(max_length=64, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "city_code_lookup"

    def __str__(self):
        return f"{self.city_code} {self.city_name}"


class TravelCategoryMapping(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="travel_categories", null=True, blank=True
    )
    vendor_pattern = models.CharField(max_length=128, blank=True)
    segment_type = models.CharField(max_length=32)
    scope = models.IntegerField()
    scope_category = models.CharField(max_length=64)
    version = models.CharField(max_length=32, default="v1")

    class Meta:
        db_table = "travel_category_mapping"

    def __str__(self):
        return f"{self.segment_type} → scope {self.scope} {self.scope_category}"


class EmissionFactorMapping(models.Model):
    """Illustrative factor table. Production would replace with versioned multi-jurisdiction set."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    activity_type = models.CharField(max_length=64)
    activity_subtype = models.CharField(max_length=64, blank=True)
    method = models.CharField(max_length=32)
    unit = models.CharField(max_length=16)
    factor = models.DecimalField(max_digits=18, decimal_places=6)
    factor_unit = models.CharField(max_length=32, default="kgCO2e")
    source = models.CharField(max_length=128, default="DEFRA 2024 (illustrative)")
    version = models.CharField(max_length=32, default="2024")
    region = models.CharField(max_length=64, blank=True, default="global")
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "emission_factor_mapping"
        unique_together = [
            ("activity_type", "activity_subtype", "method", "unit", "version", "region")
        ]
        indexes = [models.Index(fields=["activity_type", "activity_subtype"])]

    def __str__(self):
        return (
            f"{self.activity_type}/{self.activity_subtype or '-'}/{self.method}/{self.unit}"
            f" = {self.factor} {self.factor_unit}"
        )
