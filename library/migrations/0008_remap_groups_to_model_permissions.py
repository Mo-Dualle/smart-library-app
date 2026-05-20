from django.db import migrations

GROUP_LIBRARIAN = "Librarian"
GROUP_FINANCE_OFFICER = "Finance Officer"
GROUP_USER_MANAGER = "User Manager"

LIBRARY_MODELS = (
    "account",
    "author",
    "book",
    "borrow",
    "category",
    "fine",
    "readingsession",
    "reservation",
)

OLD_TO_MODELS = {
    "access_staff_dashboard": LIBRARY_MODELS,
    "manage_catalog": ("author", "book", "category"),
    "manage_circulation": ("borrow", "reservation"),
    "manage_fines_staff": ("fine",),
    "manage_members": ("account",),
    "view_members": ("account",),
    "update_members": ("account",),
    "delete_members": ("account",),
    "create_users": ("account",),
    "manage_staff_accounts": ("account", "group"),
}

GROUP_DEFAULT_OLD_CODENAMES = {
    GROUP_LIBRARIAN: (
        "access_staff_dashboard",
        "manage_catalog",
        "manage_circulation",
    ),
    GROUP_FINANCE_OFFICER: (
        "access_staff_dashboard",
        "manage_fines_staff",
    ),
    GROUP_USER_MANAGER: (
        "access_staff_dashboard",
        "view_members",
        "update_members",
        "create_users",
        "manage_staff_accounts",
    ),
}

AUTH_GROUP_CODENAMES = ("add_group", "change_group", "delete_group", "view_group")
ACCOUNT_CRUD_CODENAMES = ("add_account", "change_account", "delete_account", "view_account")
MODEL_CRUD = ("add", "change", "delete", "view")


def _perms_for_models(Permission, library_cts, models):
    ids = []
    for model in models:
        ct = library_cts.get(model)
        if not ct:
            continue
        for action in MODEL_CRUD:
            codename = f"{action}_{model}"
            try:
                ids.append(
                    Permission.objects.get(content_type=ct, codename=codename).pk
                )
            except Permission.DoesNotExist:
                pass
    return ids


def _perms_from_old_codenames(Permission, library_cts, auth_group_ct, old_codes):
    models = set()
    include_auth_group = False
    for code in old_codes:
        if code == "manage_staff_accounts":
            include_auth_group = True
        for model in OLD_TO_MODELS.get(code, ()):
            models.add(model)
    ids = _perms_for_models(Permission, library_cts, models)
    if include_auth_group and auth_group_ct:
        for codename in AUTH_GROUP_CODENAMES:
            try:
                ids.append(
                    Permission.objects.get(
                        content_type=auth_group_ct, codename=codename
                    ).pk
                )
            except Permission.DoesNotExist:
                pass
    return ids


def forwards(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")

    library_cts = {
        ct.model: ct
        for ct in ContentType.objects.filter(app_label="library", model__in=LIBRARY_MODELS)
    }
    try:
        auth_group_ct = ContentType.objects.get(app_label="auth", model="group")
    except ContentType.DoesNotExist:
        auth_group_ct = None

    all_library_ids = _perms_for_models(Permission, library_cts, LIBRARY_MODELS)
    auth_group_ids = []
    if auth_group_ct:
        for codename in AUTH_GROUP_CODENAMES:
            try:
                auth_group_ids.append(
                    Permission.objects.get(
                        content_type=auth_group_ct, codename=codename
                    ).pk
                )
            except Permission.DoesNotExist:
                pass

    for group_name, old_codes in GROUP_DEFAULT_OLD_CODENAMES.items():
        group = Group.objects.filter(name=group_name).first()
        if not group:
            continue
        perm_ids = _perms_from_old_codenames(
            Permission, library_cts, auth_group_ct, old_codes
        )
        if perm_ids:
            group.permissions.set(perm_ids)

    for group in Group.objects.exclude(
        name__in=GROUP_DEFAULT_OLD_CODENAMES.keys()
    ).prefetch_related("permissions__content_type"):
        old_codes = []
        for p in group.permissions.all():
            if (
                p.content_type.app_label == "library"
                and p.content_type.model == "account"
                and p.codename in OLD_TO_MODELS
            ):
                old_codes.append(p.codename)
        if not old_codes:
            continue
        perm_ids = _perms_from_old_codenames(
            Permission, library_cts, auth_group_ct, old_codes
        )
        if perm_ids:
            group.permissions.set(perm_ids)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("library", "0007_remove_account_custom_permissions"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(forwards, noop_reverse),
    ]
