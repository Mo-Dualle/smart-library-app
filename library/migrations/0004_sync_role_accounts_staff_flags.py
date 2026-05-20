# Historical data sync:
# users in predefined staff groups were converted to real staff accounts
# (`is_staff=True`, `is_member=False`) for admin-panel compatibility.

from django.db import migrations


ROLE_NAMES = ("Librarian", "Finance Officer", "User Manager")


def forwards(apps, schema_editor):
    Account = apps.get_model("library", "Account")
    Group = apps.get_model("auth", "Group")

    role_ids = list(
        Group.objects.filter(name__in=ROLE_NAMES).values_list("id", flat=True)
    )
    if not role_ids:
        return

    (
        Account.objects.filter(groups__id__in=role_ids)
        .filter(is_staff=False)
        .distinct()
        .update(is_staff=True, is_member=False)
    )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("library", "0003_account_staff_roles"),
    ]

    operations = [
        migrations.RunPython(forwards, noop_reverse),
    ]
