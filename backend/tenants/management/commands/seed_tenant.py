from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from tenants.models import Tenant


class Command(BaseCommand):
    help = "Idempotently create the default tenant and a seed analyst user."

    def handle(self, *args, **options):
        slug = settings.DEFAULT_TENANT_SLUG
        name = settings.DEFAULT_TENANT_NAME

        tenant, created = Tenant.objects.get_or_create(slug=slug, defaults={"name": name})
        if created:
            self.stdout.write(self.style.SUCCESS(f"Created tenant: {tenant.name} ({tenant.slug})"))
        else:
            self.stdout.write(f"Tenant already exists: {tenant.name} ({tenant.slug})")

        User = get_user_model()
        analyst, created = User.objects.get_or_create(
            username="analyst",
            defaults={
                "first_name": "Demo",
                "last_name": "Analyst",
                "email": "analyst@example.com",
                "is_staff": True,
                "is_superuser": False,
            },
        )
        if created:
            analyst.set_password("analyst")
            analyst.save()
            self.stdout.write(self.style.SUCCESS("Created seed user: analyst / analyst"))
        else:
            self.stdout.write("Seed user already exists: analyst")

        admin, created = User.objects.get_or_create(
            username="admin",
            defaults={
                "first_name": "Demo",
                "last_name": "Admin",
                "email": "admin@example.com",
                "is_staff": True,
                "is_superuser": True,
            },
        )
        if created:
            admin.set_password("admin")
            admin.save()
            self.stdout.write(self.style.SUCCESS("Created superuser: admin / admin"))
        else:
            self.stdout.write("Superuser already exists: admin")
