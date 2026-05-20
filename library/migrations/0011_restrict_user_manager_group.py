from django.db import migrations

GROUP_USER_MANAGER = "User Manager"

# User managers manage accounts only — not groups, not delete, not full admin.
USER_MANAGER_CODENAMES = (
    "view_account",
    "add_account",
    "change_account",
)


def forwards(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")

    group = Group.objects.filter(name=GROUP_USER_MANAGER).first()
    if not group:
        return

    try:
        ct = ContentType.objects.get(app_label="library", model="account")
    except ContentType.DoesNotExist:
        return

    perm_ids = list(
        Permission.objects.filter(
            content_type=ct,
            codename__in=USER_MANAGER_CODENAMES,
        ).values_list("id", flat=True)
    )
    if perm_ids:
        group.permissions.set(perm_ids)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("library", "0010_fix_default_dashboard_group_permissions"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(forwards, noop_reverse),
    ]
