# library/urls.py

from django.urls import path
from . import views

app_name = "library"

urlpatterns = [

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------
    path("register/", views.register_view, name="register"),
    path("login/",    views.login_view,    name="login"),
    path("logout/",   views.logout_view,   name="logout"),

    # ------------------------------------------------------------------
    # Dashboards
    # ------------------------------------------------------------------
    path("dashboard/",   views.dashboard_view,       name="dashboard"),
    path("admin-panel/", views.admin_dashboard_view, name="admin_dashboard"),

    # ------------------------------------------------------------------
    # Public catalog
    # ------------------------------------------------------------------
    path("",         views.landing_view,  name="landing"),
    path("books/",    views.book_list_view,   name="book_list"),
    path("books/<uuid:book_id>/",         views.book_detail_view, name="book_detail"),
    path("authors/",                      views.author_list_view,   name="author_list"),
    path("authors/<int:author_id>/",      views.author_detail_view, name="author_detail"),
    path("categories/",                   views.category_list_view, name="category_list"),

    # ------------------------------------------------------------------
    # Borrow & Return  [POST only]
    # ------------------------------------------------------------------
    path("borrow/<uuid:book_id>/",  views.borrow_book_view, name="borrow_book"),
    path("return/<int:borrow_id>/", views.return_book_view, name="return_book"),

    # ------------------------------------------------------------------
    # Reservation  [POST only]
    # ------------------------------------------------------------------
    path("reserve/<uuid:book_id>/",              views.reserve_book_view,       name="reserve_book"),
    path("reserve/cancel/<int:reservation_id>/", views.cancel_reservation_view, name="cancel_reservation"),

    # ------------------------------------------------------------------
    # Fine  [POST only]
    # ------------------------------------------------------------------
    path("fine/pay/<int:fine_id>/", views.pay_fine_view,    name="pay_fine"),
    path("fine/history/",            views.fine_history_view, name="fine_history"),

    # ------------------------------------------------------------------
    # Profile
    # ------------------------------------------------------------------
    path("profile/",      views.profile_view,      name="profile"),
    path("profile/edit/", views.profile_edit_view, name="profile_edit"),

    # ------------------------------------------------------------------
    # Reading session  [POST only]
    # ------------------------------------------------------------------
    path("reading/check-in/",  views.reading_check_in_view,  name="reading_check_in"),
    path("reading/check-out/", views.reading_check_out_view, name="reading_check_out"),

    # ------------------------------------------------------------------
    # Admin — Books CRUD
    # ------------------------------------------------------------------
    path("admin-panel/books/",                       views.admin_book_list_view,   name="admin_book_list"),
    path("admin-panel/books/add/",                   views.admin_book_create_view, name="admin_book_create"),
    path("admin-panel/books/<uuid:book_id>/edit/",   views.admin_book_edit_view,   name="admin_book_edit"),
    path("admin-panel/books/<uuid:book_id>/delete/", views.admin_book_delete_view, name="admin_book_delete"),

    # ------------------------------------------------------------------
    # Admin — Authors & Categories
    # ------------------------------------------------------------------
    path("admin-panel/authors/add/",    views.admin_author_create_view,   name="admin_author_create"),
    path("admin-panel/categories/add/", views.admin_category_create_view, name="admin_category_create"),

    # ------------------------------------------------------------------
    # Admin — Members
    # ------------------------------------------------------------------
    path("admin-panel/members/",                        views.admin_member_list_view,          name="admin_member_list"),
    path("admin-panel/members/<int:member_id>/",        views.admin_member_detail_view,        name="admin_member_detail"),
    path("admin-panel/members/<int:member_id>/toggle/", views.admin_toggle_member_active_view, name="admin_member_toggle"),
    path("admin-panel/members/<int:member_id>/delete/", views.admin_member_delete_view,        name="admin_member_delete"),

    # ------------------------------------------------------------------
    # Admin — Loans
    # ------------------------------------------------------------------
    path("admin-panel/loans/",                        views.admin_loan_list_view,    name="admin_loan_list"),
    path("admin-panel/loans/<int:borrow_id>/return/", views.admin_mark_returned_view, name="admin_mark_returned"),

    # ------------------------------------------------------------------
    # Admin — Fines, Reservations, Staff creation
    # ------------------------------------------------------------------
    path("admin-panel/fines/",          views.admin_fine_list_view,        name="admin_fine_list"),
    path("admin-panel/reservations/",   views.admin_reservation_list_view, name="admin_reservation_list"),
    path("admin-panel/staff/create/",   views.admin_create_staff_view,     name="admin_create_staff"),
    path("admin-panel/roles/",          views.admin_group_list_view,       name="admin_group_list"),
    path("admin-panel/roles/add/",      views.admin_group_create_view,     name="admin_group_create"),
    path("admin-panel/roles/<int:group_id>/edit/", views.admin_group_edit_view, name="admin_group_edit"),
    path("admin-panel/roles/<int:group_id>/delete/", views.admin_group_delete_view, name="admin_group_delete"),
    path("admin-panel/members/<int:member_id>/roles/", views.admin_member_roles_update_view, name="admin_member_roles_update"),

    # ------------------------------------------------------------------
    # Inline JSON — called from book form modals
    # ------------------------------------------------------------------
    path("admin-panel/authors/create-json/",    views.author_create_json,   name="author_create_json"),
    path("admin-panel/categories/create-json/", views.category_create_json, name="category_create_json"),
]