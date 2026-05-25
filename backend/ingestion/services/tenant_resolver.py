"""Resolve the current tenant for prototype single-tenant operation."""
from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist

from tenants.models import Tenant


def get_tenant() -> Tenant:
    """Return the default tenant; raise if not seeded."""
    try:
        return Tenant.objects.get(slug=settings.DEFAULT_TENANT_SLUG)
    except ObjectDoesNotExist:
        raise RuntimeError(
            f"Default tenant '{settings.DEFAULT_TENANT_SLUG}' not found. "
            "Run `python manage.py seed_tenant` first."
        )
