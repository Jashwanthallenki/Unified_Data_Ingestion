"""Smoke test for the three adapters against the bundled sample fixtures.

Reads the fixtures directly, runs the adapter, prints summary counts.
No DB writes — purely exercises the pipeline up to NormalizedActivity drafts.
"""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from ingestion.adapters import sap as sap_adapter
from ingestion.adapters import travel as travel_adapter
from ingestion.adapters import utility as utility_adapter
from ingestion.services.lookup_context import LookupContext
from tenants.models import Tenant


def _read_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _summarize(result, label: str):
    parse_counts = Counter(r.parse_status for r in result.rows)
    elig_counts = Counter(r.eligibility_status or "(none)" for r in result.rows)
    exclusion_counts = Counter(r.exclusion_reason for r in result.rows if r.exclusion_reason)
    total_activities = sum(len(r.activities) for r in result.rows)
    activity_status = Counter()
    confidence = Counter()
    flag_freq = Counter()
    for r in result.rows:
        for a in r.activities:
            activity_status[a.eligibility_status] += 1
            confidence[a.confidence_level] += 1
            for f in a.flags:
                flag_freq[f] += 1
    print(f"\n=== {label} ===")
    print(f"  raw rows           : {len(result.rows)}")
    print(f"  parse_status       : {dict(parse_counts)}")
    print(f"  eligibility (raw)  : {dict(elig_counts)}")
    print(f"  exclusion reasons  : {dict(exclusion_counts)}")
    print(f"  activities total   : {total_activities}")
    print(f"  activity eligibility: {dict(activity_status)}")
    print(f"  confidence levels  : {dict(confidence)}")
    print(f"  metadata           : {result.metadata}")
    print(f"  top flags          :")
    for code, count in flag_freq.most_common(15):
        print(f"     {count:>4}  {code}")


class Command(BaseCommand):
    help = "Smoke-test the SAP / utility / travel adapters against bundled fixtures."

    def handle(self, *args, **options):
        tenant = Tenant.objects.filter(slug=settings.DEFAULT_TENANT_SLUG).first()
        if tenant is None:
            raise CommandError("Run seed_tenant + load_lookups first.")

        ctx = LookupContext.load(tenant)
        fixtures = settings.BASE_DIR / "fixtures"

        # SAP MB51
        mb51_rows = _read_csv(fixtures / "sap" / "sap_mb51_fuel_movements.csv")
        mb51_result = sap_adapter.adapt_mb51(mb51_rows, ctx)
        _summarize(mb51_result, "SAP MB51 (fuel movements)")

        # SAP ME2M
        me2m_rows = _read_csv(fixtures / "sap" / "sap_me2m_procurement.csv")
        me2m_result = sap_adapter.adapt_me2m(me2m_rows, ctx)
        _summarize(me2m_result, "SAP ME2M (procurement)")

        # Utility
        utility_rows = _read_csv(fixtures / "utility" / "utility_electricity_export.csv")
        utility_result = utility_adapter.adapt_utility(utility_rows, ctx)
        _summarize(utility_result, "Utility electricity")

        # Travel
        with (fixtures / "travel" / "mock_response.json").open("r", encoding="utf-8") as f:
            travel_data = json.load(f)
        travel_result = travel_adapter.adapt_travel(travel_data.get("trips", []), ctx)
        _summarize(travel_result, "Corporate travel (mock API)")
