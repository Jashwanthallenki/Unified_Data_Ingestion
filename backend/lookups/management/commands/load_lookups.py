"""Load all lookup CSVs into the database (idempotent).

Reads from <repo>/backend/fixtures/{sap,utility,lookups}/*.csv and upserts each row.
Tenant-scoped lookups attach to the seeded default tenant.
"""
from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from lookups.models import (
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
from tenants.models import Tenant


def _decimal(value: str | None) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return Decimal(str(value).strip())
    except InvalidOperation:
        return None


def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


class Command(BaseCommand):
    help = "Load lookup tables from fixtures/. Idempotent — re-runnable."

    def add_arguments(self, parser):
        parser.add_argument(
            "--tenant",
            default=settings.DEFAULT_TENANT_SLUG,
            help="Tenant slug for tenant-scoped lookups (default: settings.DEFAULT_TENANT_SLUG).",
        )

    def handle(self, *args, **options):
        tenant_slug = options["tenant"]
        tenant = Tenant.objects.filter(slug=tenant_slug).first()
        if tenant is None:
            raise CommandError(
                f"Tenant '{tenant_slug}' not found. Run `manage.py seed_tenant` first."
            )

        fixtures = settings.BASE_DIR / "fixtures"
        self._load_movement_types(fixtures / "sap" / "movement_type_mapping.csv")
        self._load_units(fixtures / "sap" / "unit_mapping.csv", tenant)
        self._load_plants(fixtures / "sap" / "plant_lookup.csv", tenant)
        self._load_materials(fixtures / "sap" / "material_lookup.csv", tenant)
        self._load_cost_centers(fixtures / "sap" / "cost_center_lookup.csv", tenant)
        self._load_meters(fixtures / "utility" / "meter_facility_lookup.csv", tenant)
        self._load_airports(fixtures / "lookups" / "airport.csv")
        self._load_cities(fixtures / "lookups" / "city_codes.csv")
        self._load_travel_categories(fixtures / "lookups" / "travel_category.csv")
        self._load_emission_factors(fixtures / "lookups" / "emission_factors.csv")

    def _load_movement_types(self, path: Path):
        count = 0
        for row in _read_csv(path):
            MovementTypeMapping.objects.update_or_create(
                movement_type=row["movement_type"].strip(),
                defaults={
                    "description": row.get("description", ""),
                    "source_meaning": row.get("source_meaning", ""),
                    "esg_relevance": row.get("esg_relevance", "UNKNOWN"),
                    "activity_interpretation": row.get("activity_interpretation", ""),
                    "default_action": row.get("default_action", "NEEDS_ANALYST_REVIEW"),
                },
            )
            count += 1
        self.stdout.write(self.style.SUCCESS(f"MovementTypeMapping: {count} rows"))

    def _load_units(self, path: Path, tenant: Tenant):
        count = 0
        for row in _read_csv(path):
            UnitMapping.objects.update_or_create(
                tenant=tenant,
                source_unit=row["source_unit"].strip(),
                version=row.get("version", "v1"),
                defaults={
                    "normalized_unit": row.get("normalized_unit", ""),
                    "conversion_factor": _decimal(row.get("conversion_factor")) or Decimal("1"),
                    "note": row.get("note", ""),
                },
            )
            count += 1
        self.stdout.write(self.style.SUCCESS(f"UnitMapping: {count} rows"))

    def _load_plants(self, path: Path, tenant: Tenant):
        count = 0
        for row in _read_csv(path):
            PlantLookup.objects.update_or_create(
                tenant=tenant,
                plant_code=row["plant_code"].strip(),
                version=row.get("version", "v1"),
                defaults={
                    "facility_name": row.get("facility_name", ""),
                    "facility_country": row.get("facility_country", ""),
                    "region": row.get("region", ""),
                },
            )
            count += 1
        self.stdout.write(self.style.SUCCESS(f"PlantLookup: {count} rows"))

    def _load_materials(self, path: Path, tenant: Tenant):
        count = 0
        for row in _read_csv(path):
            MaterialLookup.objects.update_or_create(
                tenant=tenant,
                material_code=row["material_code"].strip(),
                version=row.get("version", "v1"),
                defaults={
                    "description": row.get("description", ""),
                    "fuel_type": row.get("fuel_type", ""),
                    "default_unit": row.get("default_unit", ""),
                    "density_kg_per_l": _decimal(row.get("density_kg_per_l")),
                },
            )
            count += 1
        self.stdout.write(self.style.SUCCESS(f"MaterialLookup: {count} rows"))

    def _load_cost_centers(self, path: Path, tenant: Tenant):
        count = 0
        for row in _read_csv(path):
            CostCenterLookup.objects.update_or_create(
                tenant=tenant,
                cost_center_code=row["cost_center_code"].strip(),
                version=row.get("version", "v1"),
                defaults={
                    "description": row.get("description", ""),
                    "business_unit": row.get("business_unit", ""),
                    "region": row.get("region", ""),
                },
            )
            count += 1
        self.stdout.write(self.style.SUCCESS(f"CostCenterLookup: {count} rows"))

    def _load_meters(self, path: Path, tenant: Tenant):
        count = 0
        for row in _read_csv(path):
            MeterFacilityLookup.objects.update_or_create(
                tenant=tenant,
                provider=row["provider"].strip(),
                account_number=row["account_number"].strip(),
                meter_number=row["meter_number"].strip(),
                version=row.get("version", "v1"),
                defaults={
                    "service_address": row.get("service_address", ""),
                    "facility_code": row.get("facility_code", ""),
                    "facility_name": row.get("facility_name", ""),
                    "facility_country": row.get("facility_country", ""),
                },
            )
            count += 1
        self.stdout.write(self.style.SUCCESS(f"MeterFacilityLookup: {count} rows"))

    def _load_airports(self, path: Path):
        count = 0
        for row in _read_csv(path):
            lat = _decimal(row.get("latitude"))
            lon = _decimal(row.get("longitude"))
            if lat is None or lon is None:
                continue
            AirportLookup.objects.update_or_create(
                iata_code=row["iata_code"].strip().upper(),
                defaults={
                    "name": row.get("name", ""),
                    "city": row.get("city", ""),
                    "country": row.get("country", ""),
                    "latitude": lat,
                    "longitude": lon,
                },
            )
            count += 1
        self.stdout.write(self.style.SUCCESS(f"AirportLookup: {count} rows"))

    def _load_cities(self, path: Path):
        count = 0
        for row in _read_csv(path):
            lat = _decimal(row.get("latitude"))
            lon = _decimal(row.get("longitude"))
            if lat is None or lon is None:
                continue
            CityCodeLookup.objects.update_or_create(
                city_code=row["city_code"].strip().upper(),
                defaults={
                    "city_name": row.get("city_name", ""),
                    "country": row.get("country", ""),
                    "latitude": lat,
                    "longitude": lon,
                },
            )
            count += 1
        self.stdout.write(self.style.SUCCESS(f"CityCodeLookup: {count} rows"))

    def _load_travel_categories(self, path: Path):
        count = 0
        for row in _read_csv(path):
            TravelCategoryMapping.objects.update_or_create(
                tenant=None,
                vendor_pattern=row.get("vendor_pattern", ""),
                segment_type=row["segment_type"].strip(),
                version=row.get("version", "v1"),
                defaults={
                    "scope": int(row.get("scope", 3)),
                    "scope_category": row.get("scope_category", "3.6 business travel"),
                },
            )
            count += 1
        self.stdout.write(self.style.SUCCESS(f"TravelCategoryMapping: {count} rows"))

    def _load_emission_factors(self, path: Path):
        count = 0
        for row in _read_csv(path):
            factor = _decimal(row.get("factor"))
            if factor is None:
                continue
            EmissionFactorMapping.objects.update_or_create(
                activity_type=row["activity_type"].strip(),
                activity_subtype=row.get("activity_subtype", "").strip(),
                method=row["method"].strip(),
                unit=row["unit"].strip(),
                version=row.get("version", "2024"),
                region=row.get("region", "global"),
                defaults={
                    "factor": factor,
                    "factor_unit": row.get("factor_unit", "kgCO2e"),
                    "source": row.get("source", "DEFRA 2024 (illustrative)"),
                    "note": row.get("note", ""),
                },
            )
            count += 1
        self.stdout.write(self.style.SUCCESS(f"EmissionFactorMapping: {count} rows"))
