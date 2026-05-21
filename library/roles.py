"""Staff access helpers using Django auth Group and Permission models."""

from __future__ import annotations

from collections import defaultdict
from functools import wraps

from django.contrib.auth.models import Group, Permission
from django.core.exceptions import PermissionDenied


# Assignable models in the group management UI (app_label -> model names)
ASSIGNABLE_APP_MODELS = {
    "library": (
        "account",
        "author",
        "book",
        "borrow",
        "category",
        "fine",
        "readingsession",
        "reservation",
    ),
    "auth": ("group",),
}

FULL_ADMIN_GROUP_NAME = "Full Admin"

# Built-in groups that must not be removed from the UI.
PROTECTED_GROUP_NAMES = (
    FULL_ADMIN_GROUP_NAME,
    "Librarian",
    "Finance Officer",
    "User Manager",
)


# ---------------------------------------------------------------------------
# Model permission strings (library + auth group management)
# ---------------------------------------------------------------------------

P_VIEW_ACCOUNT = "library.view_account"
P_ADD_ACCOUNT = "library.add_account"
P_CHANGE_ACCOUNT = "library.change_account"
P_DELETE_ACCOUNT = "library.delete_account"

P_VIEW_BOOK = "library.view_book"
P_ADD_BOOK = "library.add_book"
P_CHANGE_BOOK = "library.change_book"
P_DELETE_BOOK = "library.delete_book"

P_VIEW_AUTHOR = "library.view_author"
P_ADD_AUTHOR = "library.add_author"
P_CHANGE_AUTHOR = "library.change_author"
P_DELETE_AUTHOR = "library.delete_author"

P_VIEW_CATEGORY = "library.view_category"
P_ADD_CATEGORY = "library.add_category"
P_CHANGE_CATEGORY = "library.change_category"
P_DELETE_CATEGORY = "library.delete_category"

P_VIEW_BORROW = "library.view_borrow"
P_ADD_BORROW = "library.add_borrow"
P_CHANGE_BORROW = "library.change_borrow"
P_DELETE_BORROW = "library.delete_borrow"

P_VIEW_RESERVATION = "library.view_reservation"
P_ADD_RESERVATION = "library.add_reservation"
P_CHANGE_RESERVATION = "library.change_reservation"
P_DELETE_RESERVATION = "library.delete_reservation"

P_VIEW_FINE = "library.view_fine"
P_ADD_FINE = "library.add_fine"
P_CHANGE_FINE = "library.change_fine"
P_DELETE_FINE = "library.delete_fine"

P_VIEW_GROUP = "auth.view_group"
P_ADD_GROUP = "auth.add_group"
P_CHANGE_GROUP = "auth.change_group"
P_DELETE_GROUP = "auth.delete_group"


CATALOG_PERMS = (
    P_VIEW_BOOK, P_ADD_BOOK, P_CHANGE_BOOK, P_DELETE_BOOK,
    P_VIEW_AUTHOR, P_ADD_AUTHOR, P_CHANGE_AUTHOR, P_DELETE_AUTHOR,
    P_VIEW_CATEGORY, P_ADD_CATEGORY, P_CHANGE_CATEGORY, P_DELETE_CATEGORY,
)

CIRCULATION_PERMS = (
    P_VIEW_BORROW, P_ADD_BORROW, P_CHANGE_BORROW, P_DELETE_BORROW,
    P_VIEW_RESERVATION, P_ADD_RESERVATION, P_CHANGE_RESERVATION, P_DELETE_RESERVATION,
)

FINANCE_PERMS = (P_VIEW_FINE, P_ADD_FINE, P_CHANGE_FINE, P_DELETE_FINE)

USER_MANAGER_PERMS = (
    P_VIEW_ACCOUNT, P_ADD_ACCOUNT, P_CHANGE_ACCOUNT, P_DELETE_ACCOUNT,
    P_VIEW_GROUP, P_ADD_GROUP, P_CHANGE_GROUP, P_DELETE_GROUP,
)


# ---------------------------------------------------------------------------
# Permission queries
# ---------------------------------------------------------------------------

def _assignable_q():
    q = Permission.objects.none()
    for app_label, models in ASSIGNABLE_APP_MODELS.items():
        q = q | Permission.objects.filter(
            content_type__app_label=app_label,
            content_type__model__in=models,
        )
    return q.select_related("content_type").order_by(
        "content_type__app_label",
        "content_type__model",
        "codename",
    )


def get_assignable_permissions():
    """All permissions exposed in the group create/edit UI."""
    return _assignable_q()


def get_assignable_permission_ids() -> set[int]:
    return set(get_assignable_permissions().values_list("id", flat=True))


def group_permissions_by_app_model(permissions=None):
    """
    Nested dict for templates: {app_label: {model: [Permission, ...]}}.
    """
    if permissions is None:
        permissions = get_assignable_permissions()
    grouped = defaultdict(lambda: defaultdict(list))
    for perm in permissions:
        ct = perm.content_type
        grouped[ct.app_label][ct.model].append(perm)
    return grouped


def group_has_staff_portal_access(group: Group) -> bool:
    """True if the group grants any library or auth group-management permission."""
    return group.permissions.filter(pk__in=get_assignable_permission_ids()).exists()


def sync_user_staff_flags(user) -> None:
    """
    Set is_staff / is_member from group membership.
    Staff portal users have is_staff=True when any assigned group grants staff access.
    """
    from .models import Account

    if not user.pk:
        return
    if user.is_superuser:
        Account.objects.filter(pk=user.pk).update(is_staff=True, is_member=False)
        return

    has_portal = (
        Group.objects.filter(user=user)
        .filter(permissions__id__in=get_assignable_permission_ids())
        .exists()
    )
    Account.objects.filter(pk=user.pk).update(
        is_staff=has_portal,
        is_member=not has_portal,
    )


# ---------------------------------------------------------------------------
# User permission checks
# ---------------------------------------------------------------------------

def is_portal_staff(user) -> bool:
    """True if this account may use the in-app staff panel."""
    if not user.is_authenticated or not user.is_active:
        return False
    return bool(user.is_staff)


def user_has_perm(user, perm: str) -> bool:
    """Check a permission string (e.g. library.change_book). Superusers always pass."""
    if not user.is_authenticated or not user.is_active:
        return False
    if user.is_superuser:
        return True
    return user.has_perm(perm)


def user_has_any_perm(user, *perms: str) -> bool:
    return any(user_has_perm(user, p) for p in perms)


def user_has_all_perms(user, *perms: str) -> bool:
    return all(user_has_perm(user, p) for p in perms)


# ---------------------------------------------------------------------------
# Staff dashboard routing
# ---------------------------------------------------------------------------

STAFF_DASHBOARD_FULL = "full"
STAFF_DASHBOARD_FINANCE = "finance"
STAFF_DASHBOARD_LIBRARIAN = "librarian"
STAFF_DASHBOARD_USER_MANAGER = "user_manager"

STAFF_DASHBOARD_LABELS = {
    STAFF_DASHBOARD_FULL: "Staff overview",
    STAFF_DASHBOARD_FINANCE: "Finance dashboard",
    STAFF_DASHBOARD_LIBRARIAN: "Librarian dashboard",
    STAFF_DASHBOARD_USER_MANAGER: "User management",
}


def staff_dashboard_kind(user) -> str:
    """Which staff home page to show after login."""
    if not is_portal_staff(user):
        return STAFF_DASHBOARD_FULL

    # Superusers satisfy every permission check via user_has_perm(); without this
    # branch they would always land on finance (checked first among areas).
    if getattr(user, "is_superuser", False):
        return STAFF_DASHBOARD_FULL

    lib = user_has_any_perm(user, *CATALOG_PERMS, *CIRCULATION_PERMS)
    fin = user_has_any_perm(user, *FINANCE_PERMS)
    um = user_has_any_perm(user, *USER_MANAGER_PERMS)

    # Exactly one functional area → dedicated dashboard.
    # Multiple areas (e.g. Full Admin group) → combined staff overview.
    areas = [key for key, ok in (("fin", fin), ("lib", lib), ("um", um)) if ok]
    if len(areas) != 1:
        return STAFF_DASHBOARD_FULL
    if areas[0] == "fin":
        return STAFF_DASHBOARD_FINANCE
    if areas[0] == "lib":
        return STAFF_DASHBOARD_LIBRARIAN
    return STAFF_DASHBOARD_USER_MANAGER


def staff_dashboard_label(user) -> str:
    """Human-readable staff home label for breadcrumbs."""
    return STAFF_DASHBOARD_LABELS[staff_dashboard_kind(user)]


def can_manage_groups(user) -> bool:
    return user_has_any_perm(user, P_ADD_GROUP, P_CHANGE_GROUP)


def can_delete_group(user) -> bool:
    return user_has_perm(user, P_DELETE_GROUP)


def is_group_deletable(group_name: str) -> bool:
    return group_name not in PROTECTED_GROUP_NAMES


def can_create_staff_account(user) -> bool:
    """May open the add-staff form (create account + assign allowed groups)."""
    return user_has_perm(user, P_ADD_ACCOUNT) and user_has_perm(user, P_CHANGE_ACCOUNT)


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------

def require_permissions(*perms: str, match_any: bool = True, require_staff: bool = True):
    """
    Decorator: user must satisfy permission checks (OR by default).
    When require_staff=True, user must also be portal staff (is_staff).
    """

    if not perms:
        raise ValueError("require_permissions needs at least one permission string")

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            user = request.user
            if not user.is_authenticated:
                raise PermissionDenied
            if require_staff and not is_portal_staff(user):
                raise PermissionDenied
            checks = [user_has_perm(user, p) for p in perms]
            ok = any(checks) if match_any else all(checks)
            if not ok:
                raise PermissionDenied
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def require_staff_login(view_func):
    """Staff panel entry: authenticated + is_staff (or superuser)."""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or not is_portal_staff(request.user):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return wrapper
