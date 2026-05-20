from django.db import migrations

FULL_ADMIN_GROUP_NAME = "Full Admin"


def forwards(apps, schema_editor):
    Account = apps.get_model("library", "Account")
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")

    library_models = (
        "account",
        "author",
        "book",
        "borrow",
        "category",
        "fine",
        "readingsession",
        "reservation",
    )
    perm_ids = list(
        Permission.objects.filter(
            content_type__app_label="library",
            content_type__model__in=library_models,
        ).values_list("id", flat=True)
    )
    try:
        auth_group_ct = ContentType.objects.get(app_label="auth", model="group")
        perm_ids.extend(
            Permission.objects.filter(content_type=auth_group_ct).values_list(
                "id", flat=True
            )
        )
    except ContentType.DoesNotExist:
        pass

    if not perm_ids:
        return

    group, _ = Group.objects.get_or_create(name=FULL_ADMIN_GROUP_NAME)
    group.permissions.set(perm_ids)

    legacy_staff = Account.objects.filter(is_staff=True, is_superuser=False)
    for user in legacy_staff:
        if not user.groups.exists():
            user.groups.add(group)
        user.is_member = False
        user.save(update_fields=["is_member"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("library", "0008_remap_groups_to_model_permissions"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(forwards, noop_reverse),
    ]
