import uuid

from django.db import models


class Tenant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tenant"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


def get_default_tenant():
    """Resolve the prototype's single seeded tenant. Avoids importing settings at module top."""
    from django.conf import settings

    return Tenant.objects.filter(slug=settings.DEFAULT_TENANT_SLUG).first()
