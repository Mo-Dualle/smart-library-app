"""
Create or reset the staff superuser from environment variables.

Use when Render Shell is unavailable (free tier). Set on the web service:

  ADMIN_EMAIL    — login email (stored lowercase)
  ADMIN_PASSWORD — password for /login/
  ADMIN_USERNAME — optional, default: admin
  ADMIN_PHONE    — optional, default: 0000000000

Run automatically from build.sh on each deploy (idempotent).
"""

import os

from django.core.management.base import BaseCommand

from library.models import Account


class Command(BaseCommand):
    help = "Create or update superuser from ADMIN_EMAIL / ADMIN_PASSWORD env vars"

    def handle(self, *args, **options):
        email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
        password = os.environ.get("ADMIN_PASSWORD", "")

        if not email or not password:
            self.stdout.write(
                self.style.WARNING(
                    "bootstrap_admin: skipped (set ADMIN_EMAIL and ADMIN_PASSWORD on the service)"
                )
            )
            return

        username = os.environ.get("ADMIN_USERNAME", "admin").strip() or "admin"
        phone = os.environ.get("ADMIN_PHONE", "0000000000").strip() or "0000000000"

        user = Account.objects.filter(email__iexact=email).first()
        if user:
            user.email = email
            user.set_password(password)
            user.is_active = True
            user.is_staff = True
            user.is_superuser = True
            user.save()
            self.stdout.write(self.style.SUCCESS(f"bootstrap_admin: updated {email}"))
            return

        Account.objects.create_superuser(
            username=username,
            email=email,
            password=password,
            first_name=os.environ.get("ADMIN_FIRST_NAME", "Admin"),
            last_name=os.environ.get("ADMIN_LAST_NAME", "User"),
            phone=phone,
        )
        self.stdout.write(self.style.SUCCESS(f"bootstrap_admin: created {email}"))
