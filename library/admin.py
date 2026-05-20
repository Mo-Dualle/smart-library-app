from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.models import Group

from .models import Account, Author, Book, Borrow, Category, Fine, ReadingSession, Reservation


# ---------------------------------------------------------------------------
# Account Admin
# ---------------------------------------------------------------------------

@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    """Admin interface for managing user accounts."""
    list_display = ("email", "get_full_name", "is_member", "is_staff", "is_active", "group_count")
    list_filter = ("is_member", "is_staff", "is_active", "date_joined")
    search_fields = ("email", "first_name", "last_name", "username")
    filter_horizontal = ("groups", "user_permissions")

    fieldsets = (
        ("Personal Information", {
            "fields": ("email", "username", "first_name", "last_name", "phone", "gender", "avatar"),
        }),
        ("Account Status", {
            "fields": ("is_member", "is_staff", "is_active", "is_superuser"),
        }),
        ("Groups & Permissions", {
            "fields": ("groups", "user_permissions"),
        }),
        ("Important Dates", {
            "fields": ("last_login", "date_joined"),
        }),
    )

    readonly_fields = ("last_login", "date_joined")

    def group_count(self, obj):
        return obj.groups.count()
    group_count.short_description = "Groups"


# ---------------------------------------------------------------------------
# Django Group (built-in permissions UI)
# ---------------------------------------------------------------------------

admin.site.unregister(Group)


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin):
    filter_horizontal = ("permissions",)


# ---------------------------------------------------------------------------
# Library catalog models
# ---------------------------------------------------------------------------

@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    list_display = ("name", "book_count")
    search_fields = ("name",)

    def book_count(self, obj):
        return obj.books.count()
    book_count.short_description = "Books"


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "book_count")
    search_fields = ("name",)

    def book_count(self, obj):
        return obj.books.count()
    book_count.short_description = "Books"


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "category", "total_copies", "available_copies")
    list_filter = ("category", "author", "created_at")
    search_fields = ("title", "ISBN", "author__name")
    readonly_fields = ("created_at",)

    fieldsets = (
        ("Book Information", {
            "fields": ("title", "ISBN", "author", "category", "publisher", "summary", "image"),
        }),
        ("Stock", {
            "fields": ("total_copies", "available_copies"),
        }),
        ("Metadata", {
            "fields": ("created_at",),
        }),
    )


@admin.register(Borrow)
class BorrowAdmin(admin.ModelAdmin):
    list_display = ("member", "book", "status", "start_date", "due_date", "return_date")
    list_filter = ("status", "start_date", "due_date")
    search_fields = ("member__email", "book__title")
    readonly_fields = ("created_at",)


@admin.register(Fine)
class FineAdmin(admin.ModelAdmin):
    list_display = ("member", "borrow", "amount_due", "amount_paid", "is_settled")
    list_filter = ("created_at",)
    search_fields = ("member__email", "borrow__book__title")
    readonly_fields = ("created_at",)

    def is_settled(self, obj):
        return obj.is_settled
    is_settled.boolean = True
    is_settled.short_description = "Paid"


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ("member", "book", "status", "reserved_on", "updated_at")
    list_filter = ("status", "reserved_on")
    search_fields = ("member__email", "book__title")


@admin.register(ReadingSession)
class ReadingSessionAdmin(admin.ModelAdmin):
    list_display = ("member", "date", "time_in", "time_out", "duration_minutes")
    list_filter = ("date",)
    search_fields = ("member__email",)
    readonly_fields = ("duration_minutes", "date")
