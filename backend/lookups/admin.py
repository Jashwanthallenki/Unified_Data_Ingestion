from django.contrib import admin

from .models import (
    AirportLookup,
    CityCodeLookup,
    CostCenterLookup,
    EmissionFactorMapping,
    MaterialLookup,
    MeterFacilityLookup,
    MovementTypeMapping,
    PlantLookup,
    TravelCategoryMapping,
    UnitMapping,
)


@admin.register(PlantLookup)
class PlantLookupAdmin(admin.ModelAdmin):
    list_display = ("plant_code", "facility_name", "facility_country", "tenant", "version")
    list_filter = ("tenant", "facility_country", "version")
    search_fields = ("plant_code", "facility_name")


@admin.register(MaterialLookup)
class MaterialLookupAdmin(admin.ModelAdmin):
    list_display = ("material_code", "description", "fuel_type", "default_unit", "tenant", "version")
    list_filter = ("tenant", "fuel_type", "version")
    search_fields = ("material_code", "description")


@admin.register(UnitMapping)
class UnitMappingAdmin(admin.ModelAdmin):
    list_display = ("source_unit", "normalized_unit", "conversion_factor", "tenant", "version", "note")
    list_filter = ("normalized_unit", "version")
    search_fields = ("source_unit", "normalized_unit")


@admin.register(MovementTypeMapping)
class MovementTypeMappingAdmin(admin.ModelAdmin):
    list_display = ("movement_type", "description", "esg_relevance", "default_action")
    list_filter = ("esg_relevance", "default_action")
    search_fields = ("movement_type", "description")


@admin.register(CostCenterLookup)
class CostCenterLookupAdmin(admin.ModelAdmin):
    list_display = ("cost_center_code", "description", "business_unit", "tenant", "version")
    list_filter = ("tenant", "business_unit")
    search_fields = ("cost_center_code", "description")


@admin.register(MeterFacilityLookup)
class MeterFacilityLookupAdmin(admin.ModelAdmin):
    list_display = ("meter_number", "account_number", "provider", "facility_name", "tenant")
    list_filter = ("provider", "tenant")
    search_fields = ("meter_number", "account_number", "facility_name", "service_address")


@admin.register(AirportLookup)
class AirportLookupAdmin(admin.ModelAdmin):
    list_display = ("iata_code", "name", "city", "country")
    search_fields = ("iata_code", "name", "city", "country")


@admin.register(CityCodeLookup)
class CityCodeLookupAdmin(admin.ModelAdmin):
    list_display = ("city_code", "city_name", "country")
    search_fields = ("city_code", "city_name", "country")


@admin.register(TravelCategoryMapping)
class TravelCategoryMappingAdmin(admin.ModelAdmin):
    list_display = ("segment_type", "scope", "scope_category", "vendor_pattern", "tenant")
    list_filter = ("segment_type", "scope")


@admin.register(EmissionFactorMapping)
class EmissionFactorMappingAdmin(admin.ModelAdmin):
    list_display = (
        "activity_type", "activity_subtype", "method", "unit", "factor", "factor_unit",
        "source", "version", "region",
    )
    list_filter = ("activity_type", "method", "version", "region")
    search_fields = ("activity_type", "activity_subtype", "source")
