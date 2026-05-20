from django.db import migrations

GROUP_LIBRARIAN = "Librarian"
GROUP_FINANCE_OFFICER = "Finance Officer"
GROUP_USER_MANAGER = "User Manager"

MODEL_CRUD = ("add", "change", "delete", "view")


def _permission_ids_for_models(Permission, library_cts, model_names):
    ids = []
    for model in model_names:
        ct = library_cts.get(model)
        if not ct:
            continue
        for action in MODEL_CRUD:
            codename = f"{action}_{model}"
            perm = Permission.objects.filter(content_type=ct, codename=codename).first()
            if perm:
                ids.append(perm.id)
    return ids


def forwards(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")

    library_cts = {
        ct.model: ct
        for ct in ContentType.objects.filter(
            app_label="library",
            model__in=("account", "author", "book", "borrow", "category", "fine", "reservation"),
        )
    }
    auth_group_ct = ContentType.objects.filter(app_label="auth", model="group").first()

    librarian_ids = _permission_ids_for_models(
        Permission, library_cts, ("author", "book", "borrow", "category", "reservation")
    )
    finance_ids = _permission_ids_for_models(Permission, library_cts, ("fine",))
    user_manager_ids = _permission_ids_for_models(Permission, library_cts, ("account",))
    if auth_group_ct:
        user_manager_ids.extend(
            Permission.objects.filter(
                content_type=auth_group_ct,
                codename__in=("add_group", "change_group", "delete_group", "view_group"),
            ).values_list("id", flat=True)
        )

    mapping = {
        GROUP_LIBRARIAN: set(librarian_ids),
        GROUP_FINANCE_OFFICER: set(finance_ids),
        GROUP_USER_MANAGER: set(user_manager_ids),
    }

    for name, wanted_ids in mapping.items():
        group = Group.objects.filter(name=name).first()
        if group and wanted_ids:
            group.permissions.set(list(wanted_ids))


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0009_bootstrap_full_admin_group"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(forwards, noop_reverse),
    ]

