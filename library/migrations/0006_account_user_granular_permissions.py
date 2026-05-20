from django.db import migrations


GROUP_USER_MANAGER = "User Manager"


def forwards(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")

    try:
        ct = ContentType.objects.get(app_label="library", model="account")
    except ContentType.DoesNotExist:
        return

    perms_by_codename = {
        p.codename: p
        for p in Permission.objects.filter(content_type=ct)
    }
    group = Group.objects.filter(name=GROUP_USER_MANAGER).first()
    if not group:
        return

# Historical default policy for one existing staff group:
# - read users
# - update users
# - create users
# - manage staff role assignment
    wanted_codes = (
        "access_staff_dashboard",
        "view_members",
        "update_members",
        "create_users",
        "manage_staff_accounts",
    )
    wanted = [perms_by_codename[c] for c in wanted_codes if c in perms_by_codename]
    group.permissions.set(wanted)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("library", "0005_alter_account_options"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="account",
            options={
                "db_table": "account",
                "permissions": [
                    ("access_staff_dashboard", "Can access the staff dashboard"),
                    ("manage_catalog", "Can manage books, authors, and categories"),
                    ("manage_circulation", "Can manage loans and reservations"),
                    ("manage_fines_staff", "Can view and manage fines (staff)"),
                    ("manage_members", "Can manage library members and accounts"),
                    ("view_members", "Can view users and member profiles"),
                    ("update_members", "Can update users and member profiles"),
                    ("delete_members", "Can delete users and member profiles"),
                    ("create_users", "Can create new users"),
                    ("manage_staff_accounts", "Can create staff accounts and assign roles"),
                ],
                "verbose_name": "user",
                "verbose_name_plural": "users",
            },
        ),
        migrations.RunPython(forwards, noop_reverse),
    ]

