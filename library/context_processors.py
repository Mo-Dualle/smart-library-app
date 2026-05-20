"""Template context mirroring Django model permission checks."""

from .roles import (
    P_ADD_ACCOUNT,
    P_ADD_BOOK,
    P_ADD_GROUP,
    P_CHANGE_ACCOUNT,
    P_CHANGE_BOOK,
    P_CHANGE_BORROW,
    P_CHANGE_FINE,
    P_CHANGE_GROUP,
    P_CHANGE_RESERVATION,
    P_DELETE_ACCOUNT,
    P_VIEW_ACCOUNT,
    P_VIEW_BOOK,
    P_VIEW_GROUP,
    can_create_staff_account,
    is_portal_staff,
    user_has_any_perm,
    user_has_perm,
    CATALOG_PERMS,
    CIRCULATION_PERMS,
    FINANCE_PERMS,
    USER_MANAGER_PERMS,
)


def staff_access(request):
    """Expose booleans for navbar and admin UI; None when not applicable."""
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or not is_portal_staff(user):
        return {"staff_access": None}
    return {
        "staff_access": {
            "portal": True,
            "catalog": user_has_any_perm(user, *CATALOG_PERMS),
            "circulation": user_has_any_perm(user, *CIRCULATION_PERMS),
            "fines": user_has_any_perm(user, *FINANCE_PERMS),
            "members_read": user_has_perm(user, P_VIEW_ACCOUNT),
            "members_update": user_has_perm(user, P_CHANGE_ACCOUNT),
            "members_delete": user_has_perm(user, P_DELETE_ACCOUNT),
            "users_create": user_has_perm(user, P_ADD_ACCOUNT),
            "can_create_staff": can_create_staff_account(user),
            "members": user_has_perm(user, P_VIEW_ACCOUNT) or user_has_perm(user, P_CHANGE_ACCOUNT),
            "staff_accounts": user_has_any_perm(user, *USER_MANAGER_PERMS),
            "groups": user_has_perm(user, P_VIEW_GROUP) or user_has_perm(user, P_ADD_GROUP),
            "books": user_has_perm(user, P_VIEW_BOOK) or user_has_perm(user, P_CHANGE_BOOK),
            "books_edit": user_has_perm(user, P_ADD_BOOK) or user_has_perm(user, P_CHANGE_BOOK),
            "loans": user_has_perm(user, P_CHANGE_BORROW),
            "reservations": user_has_perm(user, P_CHANGE_RESERVATION),
            "fines_manage": user_has_perm(user, P_CHANGE_FINE),
            "manage_groups": user_has_perm(user, P_CHANGE_GROUP) or user_has_perm(user, P_ADD_GROUP),
        }
    }
