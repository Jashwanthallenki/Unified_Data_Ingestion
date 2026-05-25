"""LookupContext: in-memory snapshot of lookup tables, keyed for adapter use."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

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


@dataclass
class LookupContext:
    tenant: Tenant
    plants: dict[str, PlantLookup]
    materials: dict[str, MaterialLookup]
    unit_mappings: dict[str, UnitMapping]  # uppercase source_unit → mapping (tenant-scoped or global)
    movement_types: dict[str, MovementTypeMapping]
    cost_centers: dict[str, CostCenterLookup]
    meters: dict[tuple[str, str, str], MeterFacilityLookup]  # (provider, account, meter)
    airports: dict[str, AirportLookup]  # IATA upper
    city_codes: dict[str, CityCodeLookup]  # code upper
    travel_categories: dict[str, TravelCategoryMapping]  # segment_type lower
    emission_factors: list[EmissionFactorMapping]  # iterated; see find_emission_factor

    # versions captured for the IngestionBatch snapshot
    plant_lookup_version: Optional[str]
    material_lookup_version: Optional[str]
    unit_mapping_version: Optional[str]
    meter_mapping_version: Optional[str]
    ef_version: Optional[str]

    @classmethod
    def load(cls, tenant: Tenant) -> "LookupContext":
        plants = {
            p.plant_code.upper(): p
            for p in PlantLookup.objects.filter(tenant=tenant)
        }
        materials = {
            m.material_code.upper(): m
            for m in MaterialLookup.objects.filter(tenant=tenant)
        }
        unit_mappings = {}
        for um in UnitMapping.objects.filter(tenant__in=[tenant, None]):
            key = um.source_unit.upper()
            # tenant-specific wins
            if key not in unit_mappings or um.tenant_id is not None:
                unit_mappings[key] = um
        movement_types = {
            mt.movement_type.strip(): mt
            for mt in MovementTypeMapping.objects.all()
        }
        cost_centers = {
            cc.cost_center_code.upper(): cc
            for cc in CostCenterLookup.objects.filter(tenant=tenant)
        }
        meters = {
            (m.provider.lower(), m.account_number.upper(), m.meter_number.upper()): m
            for m in MeterFacilityLookup.objects.filter(tenant=tenant)
        }
        airports = {a.iata_code.upper(): a for a in AirportLookup.objects.all()}
        city_codes = {c.city_code.upper(): c for c in CityCodeLookup.objects.all()}
        travel_categories: dict[str, TravelCategoryMapping] = {}
        for tc in TravelCategoryMapping.objects.filter(tenant__in=[tenant, None]):
            travel_categories[tc.segment_type.lower()] = tc
        emission_factors = list(EmissionFactorMapping.objects.all())

        return cls(
            tenant=tenant,
            plants=plants,
            materials=materials,
            unit_mappings=unit_mappings,
            movement_types=movement_types,
            cost_centers=cost_centers,
            meters=meters,
            airports=airports,
            city_codes=city_codes,
            travel_categories=travel_categories,
            emission_factors=emission_factors,
            plant_lookup_version=next(iter(plants.values())).version if plants else None,
            material_lookup_version=next(iter(materials.values())).version if materials else None,
            unit_mapping_version=next(iter(unit_mappings.values())).version if unit_mappings else None,
            meter_mapping_version=next(iter(meters.values())).version if meters else None,
            ef_version=emission_factors[0].version if emission_factors else None,
        )

    def find_emission_factor(
        self,
        *,
        activity_type: str,
        activity_subtype: str | None = None,
        method: str | None = None,
        unit: str | None = None,
        region: str | None = None,
    ) -> EmissionFactorMapping | None:
        """Tier the search: exact match > drop region > drop subtype > drop method > nothing."""
        candidates = [
            ef for ef in self.emission_factors
            if ef.activity_type == activity_type
            and (activity_subtype is None or ef.activity_subtype == activity_subtype or ef.activity_subtype == "")
            and (method is None or ef.method == method)
            and (unit is None or ef.unit.lower() == (unit or "").lower())
        ]
        if not candidates:
            return None
        # Prefer exact subtype match if provided.
        if activity_subtype:
            exact = [c for c in candidates if c.activity_subtype == activity_subtype]
            if exact:
                candidates = exact
        # Prefer region match if provided.
        if region:
            region_match = [c for c in candidates if c.region.lower() == region.lower()]
            if region_match:
                return region_match[0]
            global_match = [c for c in candidates if c.region.lower() in ("", "global")]
            if global_match:
                return global_match[0]
        return candidates[0]
