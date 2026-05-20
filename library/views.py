"""
Library System — Views
All redirect() calls use the 'library:' namespace (app_name = 'library').
"""

import datetime
import logging

from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction                          # Bug fix #3: removed unused 'models'
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.html import escape
from django.views.decorators.http import require_POST, require_http_methods

from .models import (
    Account, Author, Book, Borrow,
    Category, Fine, ReadingSession, Reservation,
)
from .roles import (
    P_ADD_ACCOUNT,
    P_ADD_AUTHOR,
    P_ADD_BOOK,
    P_ADD_CATEGORY,
    P_ADD_GROUP,
    P_CHANGE_ACCOUNT,
    P_CHANGE_AUTHOR,
    P_CHANGE_BOOK,
    P_CHANGE_BORROW,
    P_CHANGE_CATEGORY,
    P_CHANGE_FINE,
    P_CHANGE_GROUP,
    P_CHANGE_RESERVATION,
    P_DELETE_ACCOUNT,
    P_DELETE_BOOK,
    P_VIEW_FINE,
    P_VIEW_ACCOUNT,
    P_VIEW_BOOK,
    P_VIEW_BORROW,
    P_VIEW_GROUP,
    STAFF_DASHBOARD_FINANCE,
    STAFF_DASHBOARD_LIBRARIAN,
    STAFF_DASHBOARD_USER_MANAGER,
    P_DELETE_GROUP,
    can_delete_group,
    can_manage_groups,
    is_group_deletable,
    get_assignable_permission_ids,
    get_assignable_permissions,
    group_has_staff_portal_access,
    group_permissions_by_app_model,
    is_portal_staff,
    require_permissions,
    require_staff_login,
    staff_dashboard_kind,
    sync_user_staff_flags,
    user_has_perm,
)

logger = logging.getLogger(__name__)

FINE_RATE_PER_DAY  = 0.50
BORROW_PERIOD_DAYS = 14


# ===========================================================================
# Private helpers
# ===========================================================================

def _apply_overdue_statuses():
    """Bulk-mark BORROWED records past due_date as OVERDUE."""
    Borrow.objects.filter(
        status=Borrow.Status.BORROWED,
        due_date__lt=datetime.date.today(),
    ).update(status=Borrow.Status.OVERDUE)


def _create_fine_if_overdue(borrow, today):
    """
    Create a Fine using get_or_create — safe against duplicate calls.
    Returns (fine | None, created: bool).
    """
    if not borrow.is_overdue:
        return None, False

    overdue_days = (today - borrow.due_date).days
    fine_amount  = round(overdue_days * FINE_RATE_PER_DAY, 2)

    borrow.has_fine = True
    borrow.save(update_fields=["has_fine"])

    fine, created = Fine.objects.get_or_create(
        borrow=borrow,
        defaults={"member": borrow.member, "amount_due": fine_amount},
    )
    return fine, created


def _fulfil_next_reservation(book):
    """
    FIFO reservation queue processor.

    When a copy becomes available after a return:
      1. Find the oldest PENDING reservation for this book.
      2. Atomically claim one copy (prevents race conditions).
      3. Auto-create a Borrow record  → reservation-to-borrow automation.
      4. Mark the reservation FULFILLED.
      5. Log notification (replace logger line with email/push in production).

    Returns the newly created Borrow or None if no reservation existed.
    """
    pending = (
        Reservation.objects
        .filter(book=book, status=Reservation.Status.PENDING)
        .order_by("reserved_on")          # FIFO: oldest first
        .select_related("member")
        .first()
    )
    if not pending:
        return None

    # Atomically claim one copy — if another request grabbed it first, bail out
    claimed = (
        Book.objects
        .filter(pk=book.pk, available_copies__gte=1)
        .update(available_copies=F("available_copies") - 1)
    )
    if not claimed:
        # Race condition: no copy left — leave reservation pending
        return None

    today  = datetime.date.today()
    borrow = Borrow.objects.create(
        book       = book,
        member     = pending.member,
        quantity   = 1,
        start_date = today,
        due_date   = today + datetime.timedelta(days=BORROW_PERIOD_DAYS),
        status     = Borrow.Status.BORROWED,
    )

    pending.status = Reservation.Status.FULFILLED
    pending.save(update_fields=["status", "updated_at"])

    logger.info(
        "[AUTO-BORROW] reservation_id=%s → borrow_id=%s member=%s book='%s'",
        pending.pk, borrow.pk, pending.member.email, book.title,
    )
    return borrow


def _decrement_copies(book, quantity):
    """
    Concurrency-safe decrement via conditional F() UPDATE.
    Returns True if the update succeeded (enough copies available).
    """
    updated = (
        Book.objects
        .filter(pk=book.pk, available_copies__gte=quantity)
        .update(available_copies=F("available_copies") - quantity)
    )
    return updated == 1


# ===========================================================================
# Decorators
# ===========================================================================

def member_required(view_func):
    """Restrict to authenticated members (is_member=True)."""
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_member:
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    wrapper.__name__ = view_func.__name__
    return wrapper


# ===========================================================================
# 1. Auth
# ===========================================================================

@require_http_methods(["GET", "POST"])
def register_view(request):
    if request.user.is_authenticated:
        return redirect("library:dashboard")

    if request.method == "POST":
        first_name = request.POST.get("first_name", "").strip()
        last_name  = request.POST.get("last_name",  "").strip()
        email      = request.POST.get("email",      "").strip().lower()
        username   = request.POST.get("username",   "").strip()
        phone      = request.POST.get("phone",      "").strip()
        gender     = request.POST.get("gender",     "").strip()
        password1  = request.POST.get("password1",  "")
        password2  = request.POST.get("password2",  "")

        errors = []
        if not all([first_name, last_name, email, username, phone, password1]):
            errors.append("All fields are required.")
        if password1 != password2:
            errors.append("Passwords do not match.")
        if len(password1) < 8:
            errors.append("Password must be at least 8 characters.")
        if Account.objects.filter(email=email).exists():
            errors.append("An account with this email already exists.")
        if Account.objects.filter(username=username).exists():
            errors.append("This username is already taken.")

        if errors:
            for error in errors:
                messages.error(request, error)
            return render(request, "auth/register.html", {"form_data": request.POST})

        try:
            user = Account.objects.create_user(
                username=username, email=email, password=password1,
                first_name=first_name, last_name=last_name,
                phone=phone, gender=gender, is_member=True,
            )
            login(request, user)
            messages.success(request, f"Welcome, {user.first_name}! Your account is ready.")
            logger.info("New member registered: %s", email)
            return redirect("library:dashboard")
        except Exception as exc:
            logger.exception("Registration failed for %s: %s", email, exc)
            messages.error(request, "Registration failed. Please try again.")

    return render(request, "auth/register.html")


@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.user.is_authenticated:
        return redirect("library:dashboard")

    if request.method == "POST":
        email    = request.POST.get("email",    "").strip().lower()
        password = request.POST.get("password", "")

        if not email or not password:
            messages.error(request, "Email and password are required.")
            return render(request, "auth/login.html")

        user = authenticate(request, username=email, password=password)

        if user is None:
            messages.error(request, "Invalid email or password.")
            logger.warning("Failed login attempt: %s", email)
            return render(request, "auth/login.html", {"email": email})

        if not user.is_active:
            messages.error(request, "Your account has been disabled. Contact the library.")
            return render(request, "auth/login.html")

        login(request, user)
        logger.info("User logged in: %s", email)

        next_url = request.GET.get("next", "").strip()
        if next_url:
            return redirect(next_url)
        staff_portal = is_portal_staff(user)
        return redirect("library:admin_dashboard" if staff_portal else "library:dashboard")

    return render(request, "auth/login.html")


@login_required
@require_POST
def logout_view(request):
    logger.info("User logged out: %s", request.user.email)
    logout(request)
    messages.success(request, "You have been logged out successfully.")
    return redirect("library:login")


# ===========================================================================
# 2. Dashboards
# ===========================================================================

@login_required
def dashboard_view(request):
    if is_portal_staff(request.user):
        return redirect("library:admin_dashboard")

    _apply_overdue_statuses()
    user = request.user

    active_borrows = (
        Borrow.objects
        .filter(member=user)
        .exclude(status=Borrow.Status.RETURNED)
        .select_related("book__author")
        .order_by("due_date")
    )
    reservations = (
        Reservation.objects
        .filter(member=user, status=Reservation.Status.PENDING)
        .select_related("book")
    )
    unpaid_fines = (
        Fine.objects
        .filter(member=user)
        .exclude(amount_paid=F("amount_due"))
        .select_related("borrow__book")
    )
    reading_sessions = ReadingSession.objects.filter(member=user).order_by("-date")[:5]
    active_session   = ReadingSession.objects.filter(member=user, time_out__isnull=True).first()

    return render(request, "member/dashboard.html", {
        "active_borrows":   active_borrows,
        "reservations":     reservations,
        "unpaid_fines":     unpaid_fines,
        "reading_sessions": reading_sessions,
        "active_session":   active_session,
        "overdue_count":    active_borrows.filter(status=Borrow.Status.OVERDUE).count(),
    })


@login_required
@require_staff_login
def admin_dashboard_view(request):
    _apply_overdue_statuses()

    dec_field = DecimalField(max_digits=14, decimal_places=2)
    outstanding_expr = ExpressionWrapper(F("amount_due") - F("amount_paid"), output_field=dec_field)
    outstanding_fines_total = Fine.objects.filter(amount_paid__lt=F("amount_due")).aggregate(
        s=Coalesce(Sum(outstanding_expr), Value(Decimal("0.00"), output_field=dec_field)),
    )["s"]

    recent_borrow_list = list(
        Borrow.objects
        .select_related("book", "member")
        .order_by("-created_at")[:10]
    )

    ctx = {
        "total_books_count":          Book.objects.count(),
        "total_users_count":          Account.objects.count(),
        "total_members_count":        Account.objects.filter(is_member=True, is_staff=False).count(),
        "total_admins_count":         Account.objects.filter(is_staff=True).count(),
        "active_borrows_count":       Borrow.objects.exclude(status=Borrow.Status.RETURNED).count(),
        "overdue_borrows_count":      Borrow.objects.filter(status=Borrow.Status.OVERDUE).count(),
        "pending_reservations_count": Reservation.objects.filter(status=Reservation.Status.PENDING).count(),
        "unpaid_fines_count":         Fine.objects.filter(amount_paid__lt=F("amount_due")).count(),
        "paid_fines_count":           Fine.objects.filter(amount_paid__gte=F("amount_due")).count(),
        "outstanding_fines_total":    outstanding_fines_total,
        "recent_borrow_list":         recent_borrow_list,
        "staff_dashboard_kind":       staff_dashboard_kind(request.user),
        "can_manage_groups":          can_manage_groups(request.user),
    }

    kind = ctx["staff_dashboard_kind"]

    if kind == STAFF_DASHBOARD_FINANCE:
        ctx["recent_fine_list"] = list(
            Fine.objects
            .select_related("borrow__book", "member")
            .order_by("-created_at")[:12]
        )
        return render(request, "admin/dashboard_finance.html", ctx)

    if kind == STAFF_DASHBOARD_LIBRARIAN:
        return render(request, "admin/dashboard_librarian.html", ctx)

    if kind == STAFF_DASHBOARD_USER_MANAGER:
        ctx["recent_members_list"] = list(
            Account.objects.filter(is_member=True, is_staff=False)
            .order_by("-date_joined")[:10]
        )
        return render(request, "admin/dashboard_user_manager.html", ctx)

    return render(request, "admin/dashboard.html", ctx)


# ===========================================================================
# 3. Books
# ===========================================================================

def book_list_view(request):
    query       = request.GET.get("q",        "").strip()
    category_id = request.GET.get("category", "").strip()
    books       = Book.objects.select_related("author", "category").order_by("title")

    if query:
        books = books.filter(
            Q(title__icontains=query) |
            Q(author__name__icontains=query) |
            Q(ISBN__icontains=query)
        )
    if category_id:
        books = books.filter(category_id=category_id)

    page = Paginator(books, 12).get_page(request.GET.get("page"))
    return render(request, "books/book_list.html", {
        "page_obj":          page,
        "categories":        Category.objects.all(),
        "query":             query,
        "selected_category": category_id,
    })


def book_detail_view(request, book_id):
    book             = get_object_or_404(Book.objects.select_related("author", "category"), pk=book_id)
    user_borrow      = None
    user_reservation = None

    if request.user.is_authenticated and request.user.is_member:
        user_borrow = (
            Borrow.objects
            .filter(member=request.user, book=book)
            .exclude(status=Borrow.Status.RETURNED)
            .first()
        )
        user_reservation = Reservation.objects.filter(
            member=request.user, book=book, status=Reservation.Status.PENDING
        ).first()

    return render(request, "books/book_detail.html", {
        "book":             book,
        "user_borrow":      user_borrow,
        "user_reservation": user_reservation,
    })


# ===========================================================================
# 4. Authors
# ===========================================================================

def author_list_view(request):
    query   = request.GET.get("q", "").strip()
    authors = Author.objects.annotate(book_count=Count("books")).order_by("name")
    if query:
        authors = authors.filter(name__icontains=query)
    page = Paginator(authors, 20).get_page(request.GET.get("page"))
    return render(request, "books/author_list.html", {"page_obj": page, "query": query})


def author_detail_view(request, author_id):
    author = get_object_or_404(Author, pk=author_id)
    books  = Book.objects.filter(author=author).select_related("category")
    return render(request, "books/author_detail.html", {"author": author, "books": books})


# ===========================================================================
# 5. Categories
# ===========================================================================

def category_list_view(request):
    categories = Category.objects.annotate(book_count=Count("books")).order_by("name")
    return render(request, "books/category_list.html", {"categories": categories})


# ===========================================================================
# 6. Borrow
# ===========================================================================

@member_required
@require_POST
def borrow_book_view(request, book_id):
    book = get_object_or_404(Book, pk=book_id)

    try:
        quantity = max(1, int(request.POST.get("quantity", 1)))
    except (ValueError, TypeError):
        quantity = 1

    if book.available_copies < quantity:
        messages.error(request, f"Only {book.available_copies} copy/copies available.")
        return redirect("library:book_detail", book_id=book_id)

    if Borrow.objects.filter(member=request.user, book=book).exclude(status=Borrow.Status.RETURNED).exists():
        messages.error(request, "You already have an active borrow for this book.")
        return redirect("library:book_detail", book_id=book_id)

    if Fine.objects.filter(member=request.user, amount_paid__lt=F("amount_due")).exists():
        messages.error(request, "You have unpaid fines. Please settle them before borrowing.")
        return redirect("library:dashboard")

    try:
        with transaction.atomic():
            if not _decrement_copies(book, quantity):
                messages.error(request, "Sorry, the last copy was just taken.")
                return redirect("library:book_detail", book_id=book_id)

            borrow = Borrow.objects.create(
                book=book, member=request.user, quantity=quantity,
                start_date=datetime.date.today(),
                due_date=datetime.date.today() + datetime.timedelta(days=BORROW_PERIOD_DAYS),
                status=Borrow.Status.BORROWED,
            )

        messages.success(request, f"You borrowed '{book.title}'. Due back by {borrow.due_date}.")
        logger.info("Borrow created: member=%s book=%s borrow_id=%s",
                    request.user.email, book.title, borrow.pk)
    except Exception as exc:
        logger.exception("Borrow failed: %s", exc)
        messages.error(request, "Something went wrong. Please try again.")

    return redirect("library:dashboard")


@member_required
@require_POST
def return_book_view(request, borrow_id):
    borrow = get_object_or_404(Borrow, pk=borrow_id, member=request.user)

    if borrow.status == Borrow.Status.RETURNED:
        messages.warning(request, "This book has already been returned.")
        return redirect("library:dashboard")

    try:
        with transaction.atomic():
            today              = datetime.date.today()
            borrow.return_date = today
            borrow.status      = Borrow.Status.RETURNED
            borrow.save(update_fields=["return_date", "status"])

            fine, _ = _create_fine_if_overdue(borrow, today)

            if fine:
                overdue_days = (today - borrow.due_date).days
                messages.warning(
                    request,
                    f"'{borrow.book.title}' returned {overdue_days} day(s) late. "
                    f"A fine of ${fine.amount_due} has been applied."
                )
            else:
                messages.success(request, f"'{borrow.book.title}' returned successfully.")

            Book.objects.filter(pk=borrow.book_id).update(
                available_copies=F("available_copies") + borrow.quantity
            )

            # FIFO auto-borrow: if someone is queued, immediately allocate
            auto_borrow = _fulfil_next_reservation(borrow.book)
            if auto_borrow:
                messages.info(
                    request,
                    f"'{borrow.book.title}' has been automatically allocated "
                    f"to the next member in the reservation queue."
                )

        logger.info("Book returned: member=%s borrow_id=%s", request.user.email, borrow_id)
    except Exception as exc:
        logger.exception("Return failed: borrow_id=%s: %s", borrow_id, exc)
        messages.error(request, "Something went wrong. Please try again.")

    return redirect("library:dashboard")


# ===========================================================================
# 7. Reservation
# ===========================================================================

@member_required
@require_POST
def reserve_book_view(request, book_id):
    book = get_object_or_404(Book, pk=book_id)

    if book.is_available:
        messages.info(request, "This book is available — you can borrow it directly.")
        return redirect("library:book_detail", book_id=book_id)

    if Reservation.objects.filter(member=request.user, book=book, status=Reservation.Status.PENDING).exists():
        messages.warning(request, "You already have a pending reservation for this book.")
        return redirect("library:book_detail", book_id=book_id)

    if Borrow.objects.filter(member=request.user, book=book).exclude(status=Borrow.Status.RETURNED).exists():
        messages.warning(request, "You currently have this book borrowed.")
        return redirect("library:book_detail", book_id=book_id)

    try:
        Reservation.objects.create(book=book, member=request.user)
        messages.success(request, f"You are now in the queue for '{book.title}'.")
        logger.info("Reservation created: member=%s book=%s", request.user.email, book.title)
    except Exception as exc:
        logger.exception("Reservation failed: %s", exc)
        messages.error(request, "Could not create reservation. Please try again.")

    return redirect("library:dashboard")


@member_required
@require_POST
def cancel_reservation_view(request, reservation_id):
    reservation = get_object_or_404(Reservation, pk=reservation_id, member=request.user)

    if reservation.status != Reservation.Status.PENDING:
        messages.warning(request, "This reservation cannot be cancelled.")
        return redirect("library:dashboard")

    reservation.status = Reservation.Status.CANCELLED
    reservation.save(update_fields=["status", "updated_at"])
    messages.success(request, f"Reservation for '{reservation.book.title}' cancelled.")
    logger.info("Reservation cancelled: reservation_id=%s member=%s",
                reservation_id, request.user.email)
    return redirect("library:dashboard")


# ===========================================================================
# 8. Fine
# ===========================================================================

@member_required
@require_POST
def pay_fine_view(request, fine_id):
    fine = get_object_or_404(Fine, pk=fine_id, member=request.user)

    if fine.is_settled:
        messages.info(request, "This fine has already been paid.")
        return redirect("library:dashboard")

    try:
        fine.amount_paid = fine.amount_due
        fine.save(update_fields=["amount_paid"])
        messages.success(request, f"Fine of ${fine.amount_due} paid successfully.")
        logger.info("Fine paid: fine_id=%s member=%s", fine_id, request.user.email)
    except Exception as exc:
        logger.exception("Fine payment failed: fine_id=%s: %s", fine_id, exc)
        messages.error(request, "Payment could not be processed. Please try again.")

    return redirect("library:fine_history")


# ===========================================================================
# 8b. Fine History
# ===========================================================================

@login_required
def fine_history_view(request):
    """Full fine history for the logged-in member."""
    fines = (
        Fine.objects
        .filter(member=request.user)
        .select_related("borrow__book")
        .order_by("-created_at")
    )
    total_due  = sum(f.amount_due  for f in fines)
    total_paid = sum(f.amount_paid for f in fines)
    return render(request, "member/fine_history.html", {
        "fines":      fines,
        "total_due":  total_due,
        "total_paid": total_paid,
        "total_outstanding": total_due - total_paid,
    })


# ===========================================================================
# 9. Reading Session
# ===========================================================================

@member_required
@require_POST
def reading_check_in_view(request):
    if ReadingSession.objects.filter(member=request.user, time_out__isnull=True).exists():
        messages.warning(request, "You already have an active reading session.")
        return redirect("library:dashboard")

    try:
        ReadingSession.objects.create(member=request.user, time_in=timezone.now())
        messages.success(request, "Reading session started.")
        logger.info("Reading check-in: member=%s", request.user.email)
    except Exception as exc:
        logger.exception("Check-in failed: %s", exc)
        messages.error(request, "Could not start reading session.")

    return redirect("library:dashboard")


@member_required
@require_POST
def reading_check_out_view(request):
    session = ReadingSession.objects.filter(member=request.user, time_out__isnull=True).first()

    if not session:
        messages.warning(request, "No active reading session found.")
        return redirect("library:dashboard")

    try:
        session.time_out = timezone.now()
        session.save(update_fields=["time_out"])
        messages.success(request, f"Reading session ended. Duration: {session.duration_minutes} min.")
        logger.info("Reading check-out: member=%s", request.user.email)
    except Exception as exc:
        logger.exception("Check-out failed: %s", exc)
        messages.error(request, "Could not end reading session.")

    return redirect("library:dashboard")


# ===========================================================================
# 10. Admin — Books
# ===========================================================================

@login_required
@require_permissions(P_VIEW_BOOK, P_CHANGE_BOOK, P_ADD_BOOK)
def admin_book_list_view(request):
    _apply_overdue_statuses()
    query = request.GET.get("q", "").strip()
    books = Book.objects.select_related("author", "category")
    if query:
        books = books.filter(Q(title__icontains=query) | Q(ISBN__icontains=query))
    page = Paginator(books, 20).get_page(request.GET.get("page"))
    return render(request, "admin/book_list.html", {"page_obj": page, "query": query})


@login_required
@require_permissions(P_VIEW_BOOK, P_CHANGE_BOOK, P_ADD_BOOK)
@require_http_methods(["GET", "POST"])
def admin_book_create_view(request):
    if request.method == "POST":
        try:
            title     = request.POST.get("title",     "").strip()
            ISBN      = request.POST.get("ISBN",      "").strip()
            publisher = request.POST.get("publisher", "").strip()
            summary   = request.POST.get("summary",   "").strip()
            total     = int(request.POST.get("total_copies", 1))
            author    = get_object_or_404(Author,   pk=request.POST.get("author_id"))
            category  = get_object_or_404(Category, pk=request.POST.get("category_id"))

            if not title or not ISBN:
                raise ValueError("Title and ISBN are required.")

            # Bug fix #4: only pass image kwarg if a file was actually uploaded
            kwargs = dict(
                title=title, summary=summary, ISBN=ISBN,
                publisher=publisher, author=author, category=category,
                total_copies=total, available_copies=total,
            )
            if request.FILES.get("image"):
                kwargs["image"] = request.FILES["image"]

            book = Book.objects.create(**kwargs)
            messages.success(request, f"'{book.title}' added to the catalog.")
            logger.info("Book created: %s by staff %s", book.title, request.user.email)
            return redirect("library:admin_book_list")

        except ValueError as exc:
            messages.error(request, str(exc))
        except Exception as exc:
            logger.exception("Book creation failed: %s", exc)
            messages.error(request, "Could not create book. Please check the form.")

    return render(request, "admin/book_form.html", {
        "authors":    Author.objects.all(),
        "categories": Category.objects.all(),
    })


@login_required
@require_permissions(P_VIEW_BOOK, P_CHANGE_BOOK, P_ADD_BOOK)
@require_http_methods(["GET", "POST"])
def admin_book_edit_view(request, book_id):
    book = get_object_or_404(Book, pk=book_id)

    if request.method == "POST":
        try:
            book.title     = request.POST.get("title",     book.title).strip()
            book.summary   = request.POST.get("summary",   book.summary).strip()
            book.ISBN      = request.POST.get("ISBN",      book.ISBN).strip()
            book.publisher = request.POST.get("publisher", book.publisher).strip()
            book.author    = get_object_or_404(Author,   pk=request.POST.get("author_id"))
            book.category  = get_object_or_404(Category, pk=request.POST.get("category_id"))

            if not book.title or not book.ISBN:
                raise ValueError("Title and ISBN are required.")

            new_total = int(request.POST.get("total_copies", book.total_copies))
            diff = new_total - book.total_copies
            book.total_copies     = new_total
            book.available_copies = max(0, book.available_copies + diff)

            if request.FILES.get("image"):
                book.image = request.FILES["image"]

            book.save()
            messages.success(request, f"'{book.title}' updated successfully.")
            logger.info("Book edited: %s by staff %s", book.pk, request.user.email)
            return redirect("library:admin_book_list")

        except ValueError as exc:
            messages.error(request, str(exc))
        except Exception as exc:
            logger.exception("Book edit failed: book_id=%s: %s", book_id, exc)
            messages.error(request, "Could not update book.")

    return render(request, "admin/book_form.html", {
        "book":       book,
        "authors":    Author.objects.all(),
        "categories": Category.objects.all(),
    })


@login_required
@require_permissions(P_DELETE_BOOK)
@require_POST
def admin_book_delete_view(request, book_id):
    book  = get_object_or_404(Book, pk=book_id)
    title = book.title

    if Borrow.objects.filter(book=book).exclude(status=Borrow.Status.RETURNED).exists():
        messages.error(request, f"Cannot delete '{title}' — it has active borrows.")
        return redirect("library:admin_book_list")

    try:
        book.delete()
        messages.success(request, f"'{title}' deleted.")
        logger.info("Book deleted: %s by staff %s", book_id, request.user.email)
    except Exception as exc:
        logger.exception("Book delete failed: %s", exc)
        messages.error(request, "Could not delete book.")

    return redirect("library:admin_book_list")


# ===========================================================================
# 11. Admin — Authors & Categories
# ===========================================================================

@login_required
@require_permissions(P_ADD_AUTHOR, P_CHANGE_AUTHOR)
@require_http_methods(["GET", "POST"])
def admin_author_create_view(request):
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        if not name:
            messages.error(request, "Author name is required.")
            return render(request, "admin/author_form.html")
        try:
            author = Author.objects.create(name=name)
            messages.success(request, f"Author '{author.name}' added.")
            logger.info("Author created: %s by staff %s", author.name, request.user.email)
            return redirect("library:admin_book_list")
        except Exception as exc:
            logger.exception("Author creation failed: %s", exc)
            messages.error(request, "Could not create author.")
    return render(request, "admin/author_form.html")


@login_required
@require_permissions(P_ADD_CATEGORY, P_CHANGE_CATEGORY)
@require_http_methods(["GET", "POST"])
def admin_category_create_view(request):
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        if not name:
            messages.error(request, "Category name is required.")
            return render(request, "admin/category_form.html")
        try:
            category = Category.objects.create(name=name)
            messages.success(request, f"Category '{category.name}' added.")
            logger.info("Category created: %s by staff %s", category.name, request.user.email)
            return redirect("library:admin_book_list")
        except Exception as exc:
            logger.exception("Category creation failed: %s", exc)
            messages.error(request, "Could not create category.")
    return render(request, "admin/category_form.html")


# ===========================================================================
# 12. Admin — Members
# ===========================================================================

@login_required
@require_permissions(P_VIEW_ACCOUNT, P_CHANGE_ACCOUNT)
def admin_member_list_view(request):
    """
    Unified user list — filterable by role:
      ?role=member  → library members only
      ?role=admin   → staff / admin accounts only
      (no filter)   → all accounts
    """
    query       = request.GET.get("q",    "").strip()
    role_filter = request.GET.get("role", "").strip()

    role_staff_q = Q(is_staff=True)
    users = (
        Account.objects
        .filter(Q(is_staff=False) | role_staff_q)
        .distinct()
        .order_by("last_name", "first_name")
        .prefetch_related("groups")
    )

    if role_filter == "member":
        users = users.filter(is_member=True, is_staff=False)
    elif role_filter == "admin":
        users = users.filter(role_staff_q).distinct()

    if query:
        users = users.filter(
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query)  |
            Q(email__icontains=query)       |
            Q(username__icontains=query)
        )

    page = Paginator(users, 20).get_page(request.GET.get("page"))
    return render(request, "admin/member_list.html", {
        "page_obj":    page,
        "query":       query,
        "role_filter": role_filter,
        "current_user_id": request.user.id,
        "can_create_users": user_has_perm(request.user, P_ADD_ACCOUNT),
        "can_update_members": user_has_perm(request.user, P_CHANGE_ACCOUNT),
        "can_delete_members": user_has_perm(request.user, P_DELETE_ACCOUNT),
        "total_all":     Account.objects.filter(Q(is_staff=False) | role_staff_q).distinct().count(),
        "total_members": Account.objects.filter(is_member=True, is_staff=False).count(),
        "total_admins":  Account.objects.filter(role_staff_q).distinct().count(),
    })


@login_required
@require_permissions(
    P_VIEW_ACCOUNT,
    P_CHANGE_ACCOUNT,
    P_CHANGE_BORROW,
    P_CHANGE_FINE,
)
def admin_member_detail_view(request, member_id):
    member       = get_object_or_404(Account, pk=member_id, is_member=True)
    borrows      = Borrow.objects.filter(member=member).select_related("book").order_by("-created_at")
    fines        = Fine.objects.filter(member=member).select_related("borrow__book")
    reservations = Reservation.objects.filter(member=member).select_related("book").order_by("-reserved_on")
    return render(request, "admin/member_detail.html", {
        "member": member, "borrows": borrows,
        "fines": fines, "reservations": reservations,
        "can_manage_members": user_has_perm(request.user, P_CHANGE_ACCOUNT),
        "can_delete_members": user_has_perm(request.user, P_DELETE_ACCOUNT),
        "can_manage_staff_accounts": can_manage_groups(request.user),
        "all_groups": _get_assignable_groups(request.user) if can_manage_groups(request.user) else None,
    })


@login_required
@require_permissions(P_CHANGE_ACCOUNT)
@require_POST
def admin_toggle_member_active_view(request, member_id):
    member           = get_object_or_404(Account, pk=member_id)
    member.is_active = not member.is_active
    member.save(update_fields=["is_active"])
    state = "enabled" if member.is_active else "disabled"
    messages.success(request, f"{member.get_full_name()}'s account has been {state}.")
    logger.info("Member %s: id=%s by staff %s", state, member_id, request.user.email)
    return redirect("library:admin_member_list")


@login_required
@require_permissions(P_DELETE_ACCOUNT)
@require_POST
def admin_member_delete_view(request, member_id):
    member = get_object_or_404(Account, pk=member_id)
    if member.pk == request.user.pk:
        messages.error(request, "You cannot delete your own account.")
        return redirect("library:admin_member_list")
    if member.is_superuser:
        messages.error(request, "Superuser accounts cannot be deleted.")
        return redirect("library:admin_member_list")

    full_name = member.get_full_name() or member.email
    try:
        member.delete()
        messages.success(request, f"User '{full_name}' has been deleted.")
        logger.info("Member deleted: id=%s by staff %s", member_id, request.user.email)
    except Exception as exc:
        logger.exception("Member delete failed: id=%s: %s", member_id, exc)
        messages.error(request, "Could not delete user. Please try again.")
    return redirect("library:admin_member_list")


@login_required
@require_permissions(P_CHANGE_ACCOUNT)
@require_POST
def admin_member_roles_update_view(request, member_id):
    """
    Update the auth groups (roles) for a user.
    """
    member = get_object_or_404(Account, pk=member_id)
    group_ids = request.POST.getlist("groups")

    try:
        requested_ids = {int(x) for x in group_ids}
    except Exception as exc:
        logger.exception("Group update invalid ids for member_id=%s: %s", member_id, exc)
        messages.error(request, "Invalid group selection.")
        return redirect("library:admin_member_detail", member_id=member_id)

    allowed_ids = _get_assignable_group_ids(request.user)
    if not requested_ids.issubset(allowed_ids):
        raise PermissionDenied

    groups = list(Group.objects.filter(id__in=requested_ids))
    member.groups.set(groups)
    sync_user_staff_flags(member)

    messages.success(request, "Groups updated successfully.")
    logger.info("Groups updated for member_id=%s by staff %s", member_id, request.user.email)

    return redirect("library:admin_member_detail", member_id=member_id)


# ===========================================================================
# 13. Admin — Loans
# ===========================================================================

@login_required
@require_permissions(P_VIEW_BORROW, P_CHANGE_BORROW, P_CHANGE_RESERVATION)
def admin_loan_list_view(request):
    _apply_overdue_statuses()
    status_filter = request.GET.get("status", "").strip()
    borrows       = Borrow.objects.select_related("book", "member").order_by("-created_at")

    valid_statuses = [s[0] for s in Borrow.Status.choices]
    if status_filter in valid_statuses:
        borrows = borrows.filter(status=status_filter)

    page = Paginator(borrows, 25).get_page(request.GET.get("page"))
    return render(request, "admin/loan_list.html", {
        "page_obj":       page,
        "status_filter":  status_filter,
        "status_choices": Borrow.Status.choices,
    })


@login_required
@require_permissions(P_VIEW_BORROW, P_CHANGE_BORROW, P_CHANGE_RESERVATION)
@require_POST
def admin_mark_returned_view(request, borrow_id):
    borrow = get_object_or_404(Borrow, pk=borrow_id)

    if borrow.status == Borrow.Status.RETURNED:
        messages.warning(request, "Already marked as returned.")
        return redirect("library:admin_loan_list")

    try:
        with transaction.atomic():
            today              = datetime.date.today()
            borrow.return_date = today
            borrow.status      = Borrow.Status.RETURNED
            borrow.save(update_fields=["return_date", "status"])

            _create_fine_if_overdue(borrow, today)

            Book.objects.filter(pk=borrow.book_id).update(
                available_copies=F("available_copies") + borrow.quantity
            )
            _fulfil_next_reservation(borrow.book)

        messages.success(request, f"Borrow #{borrow_id} marked as returned.")
        logger.info("Staff marked returned: borrow_id=%s by %s", borrow_id, request.user.email)
    except Exception as exc:
        logger.exception("Admin return failed: borrow_id=%s: %s", borrow_id, exc)
        messages.error(request, "Could not process return.")

    return redirect("library:admin_loan_list")



# ===========================================================================
# Landing page
# ===========================================================================

def landing_view(request):
    """
    Public landing page.
    Authenticated users are sent straight to their dashboard.
    """
    if request.user.is_authenticated:
        staff_portal = is_portal_staff(request.user)
        return redirect("library:admin_dashboard" if staff_portal else "library:dashboard")

    from django.db.models import Sum
    total_books   = Book.objects.count()
    total_members = Account.objects.filter(is_member=True).count()
    total_borrows = Borrow.objects.count()

    return render(request, "landing.html", {
        "total_books":   total_books   or 0,
        "total_members": total_members or 0,
        "total_borrows": total_borrows or 0,
    })


# ===========================================================================
# Profile
# ===========================================================================

@login_required
def profile_view(request):
    """Display the logged-in user's profile."""
    borrow_count      = Borrow.objects.filter(member=request.user).count()
    active_borrow_count = Borrow.objects.filter(
        member=request.user).exclude(status=Borrow.Status.RETURNED).count()
    fine_count        = Fine.objects.filter(member=request.user).count()
    reservation_count = Reservation.objects.filter(member=request.user).count()

    return render(request, "member/profile.html", {
        "borrow_count":       borrow_count,
        "active_borrow_count": active_borrow_count,
        "fine_count":         fine_count,
        "reservation_count":  reservation_count,
    })


@login_required
@require_http_methods(["GET", "POST"])
def profile_edit_view(request):
    """Edit profile details and avatar."""
    user = request.user

    if request.method == "POST":
        first_name = request.POST.get("first_name", "").strip()
        last_name  = request.POST.get("last_name",  "").strip()
        phone      = request.POST.get("phone",      "").strip()
        gender     = request.POST.get("gender",     "").strip()
        avatar     = request.FILES.get("avatar")

        errors = []
        if not first_name: errors.append("First name is required.")
        if not last_name:  errors.append("Last name is required.")
        if not phone:      errors.append("Phone number is required.")

        if errors:
            for e in errors:
                messages.error(request, e)
            return render(request, "member/profile_edit.html")

        try:
            user.first_name = first_name
            user.last_name  = last_name
            user.phone      = phone
            user.gender     = gender

            if avatar:
                # Delete old avatar if it is not the default
                if user.avatar and "default" not in user.avatar.name:
                    user.avatar.delete(save=False)
                user.avatar = avatar

            user.save(update_fields=["first_name", "last_name", "phone", "gender", "avatar"])
            messages.success(request, "Profile updated successfully.")
            logger.info("Profile updated: %s", user.email)
            return redirect("library:profile")

        except Exception as exc:
            logger.exception("Profile update failed: %s", exc)
            messages.error(request, "Could not update profile. Please try again.")

    return render(request, "member/profile_edit.html")

# ===========================================================================
# Admin — Fine List (filterable)
# ===========================================================================

@login_required
@require_permissions(P_VIEW_FINE, P_CHANGE_FINE)
def admin_fine_list_view(request):
    """All fines filterable by paid / unpaid."""
    status_filter = request.GET.get("status", "").strip()
    query         = request.GET.get("q", "").strip()

    fines = (
        Fine.objects
        .select_related("borrow__book", "member")
        .order_by("-created_at")
    )

    if status_filter == "unpaid":
        fines = fines.filter(amount_paid__lt=F("amount_due"))
    elif status_filter == "paid":
        fines = fines.filter(amount_paid__gte=F("amount_due"))

    if query:
        fines = fines.filter(
            Q(member__first_name__icontains=query) |
            Q(member__last_name__icontains=query)  |
            Q(member__email__icontains=query)       |
            Q(borrow__book__title__icontains=query)
        )

    page = Paginator(fines, 25).get_page(request.GET.get("page"))
    return render(request, "admin/fine_list.html", {
        "page_obj":     page,
        "status_filter": status_filter,
        "query":        query,
        "total_unpaid": Fine.objects.filter(amount_paid__lt=F("amount_due")).count(),
        "total_paid":   Fine.objects.filter(amount_paid__gte=F("amount_due")).count(),
    })


# ===========================================================================
# Admin — Reservation List
# ===========================================================================

@login_required
@require_permissions(P_VIEW_BORROW, P_CHANGE_BORROW, P_CHANGE_RESERVATION)
def admin_reservation_list_view(request):
    """All reservations filterable by status."""
    status_filter = request.GET.get("status", "").strip()
    query         = request.GET.get("q", "").strip()

    reservations = (
        Reservation.objects
        .select_related("book", "member")
        .order_by("reserved_on")
    )

    if status_filter in [s[0] for s in Reservation.Status.choices]:
        reservations = reservations.filter(status=status_filter)

    if query:
        reservations = reservations.filter(
            Q(member__first_name__icontains=query) |
            Q(member__last_name__icontains=query)  |
            Q(member__email__icontains=query)       |
            Q(book__title__icontains=query)
        )

    page = Paginator(reservations, 25).get_page(request.GET.get("page"))
    return render(request, "admin/reservation_list.html", {
        "page_obj":       page,
        "status_filter":  status_filter,
        "status_choices": Reservation.Status.choices,
        "query":          query,
    })


# ===========================================================================
# Admin — Create Staff Account
# ===========================================================================

@login_required
@require_permissions(P_ADD_ACCOUNT, P_CHANGE_ACCOUNT, match_any=False)
@require_http_methods(["GET", "POST"])
def admin_create_staff_view(request):
    """
    Create a staff account using built-in Django groups.
    """
    selectable_groups = _get_assignable_groups(request.user)

    if request.method == "POST":
        first_name = request.POST.get("first_name", "").strip()
        last_name  = request.POST.get("last_name",  "").strip()
        email      = request.POST.get("email",      "").strip().lower()
        username   = request.POST.get("username",   "").strip()
        phone      = request.POST.get("phone",      "").strip()
        password1  = request.POST.get("password1",  "")
        password2  = request.POST.get("password2",  "")
        selected_group_ids = request.POST.getlist("groups")

        errors = []
        if not all([first_name, last_name, email, username, password1]):
            errors.append("All fields are required.")
        if password1 != password2:
            errors.append("Passwords do not match.")
        if len(password1) < 8:
            errors.append("Password must be at least 8 characters.")
        if Account.objects.filter(email=email).exists():
            errors.append("An account with this email already exists.")
        if Account.objects.filter(username=username).exists():
            errors.append("This username is already taken.")
        if not selected_group_ids:
            errors.append("Select at least one role group.")

        if errors:
            for e in errors:
                messages.error(request, e)
            return render(request, "admin/create_staff.html", {
                "form_data": request.POST,
                "selectable_groups": selectable_groups,
                "selected_group_ids": selected_group_ids,
            })

        try:
            requested_ids = {int(x) for x in selected_group_ids}
        except (TypeError, ValueError):
            messages.error(request, "Invalid role group selection.")
            return render(request, "admin/create_staff.html", {
                "form_data": request.POST,
                "selectable_groups": selectable_groups,
                "selected_group_ids": selected_group_ids,
            })

        allowed_ids = set(selectable_groups.values_list("id", flat=True))
        if not requested_ids.issubset(allowed_ids):
            raise PermissionDenied

        try:
            user = Account.objects.create_user(
                username   = username,
                email      = email,
                password   = password1,
                first_name = first_name,
                last_name  = last_name,
                phone      = phone or "",
                is_staff   = False,
                is_member  = True,
            )
            groups = list(Group.objects.filter(id__in=requested_ids))
            user.groups.set(groups)
            sync_user_staff_flags(user)

            messages.success(
                request,
                f"Staff account for {user.get_full_name()} created successfully.",
            )
            logger.info(
                "Staff account created: %s by %s",
                email,
                request.user.email,
            )
            return redirect("library:admin_dashboard")

        except Exception as exc:
            logger.exception("Staff creation failed: %s", exc)
            messages.error(request, "Could not create account. Please try again.")

    return render(request, "admin/create_staff.html", {
        "form_data": None,
        "selectable_groups": selectable_groups,
        "selected_group_ids": [],
    })


# ===========================================================================
# Admin — Groups (list / create / edit)
# ===========================================================================


def _is_privileged_group_editor(user) -> bool:
    """Only superusers may bypass delegation restrictions."""
    return bool(user and user.is_authenticated and user.is_superuser)


def _user_assignable_permission_ids(user) -> set[int]:
    if not user or not user.is_authenticated:
        return set()
    if user.is_superuser:
        return get_assignable_permission_ids()
    return {
        p.id
        for p in get_assignable_permissions()
        if user.has_perm(f"{p.content_type.app_label}.{p.codename}")
    }


def _get_assignable_group_ids(user) -> set[int]:
    """
    Delegation rule (least privilege):
    - privileged editors can assign any group
    - others can only assign groups whose permission set is a subset of theirs
    """
    if not user or not user.is_authenticated:
        return set()

    if _is_privileged_group_editor(user):
        return set(Group.objects.values_list("id", flat=True))

    allowed_perm_ids = _user_assignable_permission_ids(user)
    if not allowed_perm_ids:
        return set()

    assignable_ids = get_assignable_permission_ids()
    manageable_ids: set[int] = set()
    for g in Group.objects.prefetch_related("permissions").all():
        group_perm_ids = {
            p.id for p in g.permissions.all() if p.id in assignable_ids
        }
        if group_perm_ids and group_perm_ids.issubset(allowed_perm_ids):
            manageable_ids.add(g.id)

    return manageable_ids


def _get_assignable_groups(user):
    ids = _get_assignable_group_ids(user)
    if not ids:
        return Group.objects.none()
    qs = Group.objects.filter(id__in=ids).order_by("name")
    if user and user.is_authenticated and not user.is_superuser:
        from .roles import FULL_ADMIN_GROUP_NAME
        qs = qs.exclude(name=FULL_ADMIN_GROUP_NAME)
    return qs


def _parse_selected_permission_ids(request, user=None) -> set[int]:
    assignable = get_assignable_permission_ids()
    if user and not user.is_superuser:
        # Non-superusers may only grant permissions they already hold.
        assignable = assignable.intersection(_user_assignable_permission_ids(user))
    selected = set()
    for raw in request.POST.getlist("perm_id"):
        try:
            pid = int(raw)
        except (TypeError, ValueError):
            continue
        if pid in assignable:
            selected.add(pid)
    return selected


def _group_form_context(mode, *, user=None, group=None, form_data=None, selected_perm_ids=None):
    permissions = get_assignable_permissions()
    if user and not user.is_superuser:
        allowed_ids = _user_assignable_permission_ids(user)
        permissions = [p for p in permissions if p.id in allowed_ids]

    permission_groups = group_permissions_by_app_model(permissions)
    permission_sections = []
    for app_label, model_map in permission_groups.items():
        models = []
        for model_name, perms in model_map.items():
            models.append(
                {
                    "model_name": model_name,
                    "perms": list(perms),
                }
            )
        permission_sections.append(
            {
                "app_label": app_label,
                "models": models,
            }
        )

    return {
        "mode": mode,
        "group": group,
        "form_data": form_data,
        "permission_sections": permission_sections,
        "selected_perm_ids": selected_perm_ids or set(),
    }


@login_required
@require_permissions(P_VIEW_GROUP, P_ADD_GROUP, P_CHANGE_GROUP)
def admin_group_list_view(request):
    """List all auth groups and their Django permissions."""
    assignable_ids = get_assignable_permission_ids()
    groups = Group.objects.prefetch_related("permissions__content_type").order_by("name")

    rows = []
    for g in groups:
        g_perms = [p for p in g.permissions.all() if p.id in assignable_ids]
        user_count = Account.objects.filter(groups=g).count()
        rows.append(
            {
                "group": g,
                "permissions": sorted(g_perms, key=lambda p: (p.content_type.model, p.codename)),
                "is_staff_portal": group_has_staff_portal_access(g),
                "user_count": user_count,
                "can_delete": (
                    can_delete_group(request.user)
                    and is_group_deletable(g.name)
                    and user_count == 0
                ),
            }
        )

    return render(request, "admin/group_list.html", {
        "rows": rows,
        "can_manage_groups": _is_privileged_group_editor(request.user),
        "can_delete_groups": can_delete_group(request.user),
    })


@login_required
@require_permissions(P_ADD_GROUP, P_CHANGE_GROUP)
@require_http_methods(["GET", "POST"])
def admin_group_create_view(request):
    """Create a new auth group with selected Django permissions."""
    if not user_has_perm(request.user, P_ADD_GROUP):
        raise PermissionDenied

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        selected_ids = _parse_selected_permission_ids(request, request.user)

        errors = []
        if not name:
            errors.append("Group name is required.")
        if Group.objects.filter(name__iexact=name).exists():
            errors.append("A group with this name already exists.")
        if not selected_ids:
            errors.append("Select at least one permission for this group.")

        if errors:
            for e in errors:
                messages.error(request, e)
            return render(
                request,
                "admin/group_form.html",
                _group_form_context("create", user=request.user, form_data=request.POST, selected_perm_ids=selected_ids),
            )

        try:
            group = Group.objects.create(name=name)
            group.permissions.set(
                Permission.objects.filter(pk__in=selected_ids)
            )
            for user in Account.objects.filter(groups=group):
                sync_user_staff_flags(user)
            messages.success(request, f"Group '{group.name}' created successfully.")
            return redirect("library:admin_group_list")
        except Exception as exc:
            logger.exception("Group creation failed: %s", exc)
            messages.error(request, "Could not create group. Please try again.")

    return render(request, "admin/group_form.html", _group_form_context("create", user=request.user))


@login_required
@require_permissions(P_CHANGE_GROUP)
@require_http_methods(["GET", "POST"])
def admin_group_edit_view(request, group_id):
    """Edit an existing auth group and its Django permissions."""
    group = get_object_or_404(Group, pk=group_id)

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        selected_ids = _parse_selected_permission_ids(request, request.user)

        errors = []
        if not name:
            errors.append("Group name is required.")
        if Group.objects.filter(name__iexact=name).exclude(pk=group.pk).exists():
            errors.append("Another group with this name already exists.")
        if not selected_ids:
            errors.append("Select at least one permission for this group.")

        if errors:
            for e in errors:
                messages.error(request, e)
            return render(
                request,
                "admin/group_form.html",
                _group_form_context(
                    "edit",
                    user=request.user,
                    group=group,
                    form_data=request.POST,
                    selected_perm_ids=selected_ids,
                ),
            )

        try:
            group.name = name
            group.save(update_fields=["name"])
            group.permissions.set(
                Permission.objects.filter(pk__in=selected_ids)
            )
            for user in Account.objects.filter(groups=group):
                sync_user_staff_flags(user)
            messages.success(request, f"Group '{group.name}' updated successfully.")
            return redirect("library:admin_group_list")
        except Exception as exc:
            logger.exception("Group update failed: group_id=%s: %s", group_id, exc)
            messages.error(request, "Could not update group. Please try again.")

    assignable_ids = get_assignable_permission_ids()
    current_ids = {
        p.id for p in group.permissions.all() if p.id in assignable_ids
    }
    return render(
        request,
        "admin/group_form.html",
        _group_form_context("edit", user=request.user, group=group, selected_perm_ids=current_ids),
    )


@login_required
@require_permissions(P_DELETE_GROUP)
@require_POST
def admin_group_delete_view(request, group_id):
    """Delete an auth group when it has no members and is not a protected system group."""
    group = get_object_or_404(Group, pk=group_id)
    name = group.name

    if not is_group_deletable(name):
        messages.error(request, f"Group '{name}' is a protected system group and cannot be deleted.")
        return redirect("library:admin_group_list")

    user_count = Account.objects.filter(groups=group).count()
    if user_count > 0:
        messages.error(
            request,
            f"Cannot delete '{name}' — {user_count} user(s) still belong to this group. Reassign them first.",
        )
        return redirect("library:admin_group_list")

    try:
        group.delete()
        messages.success(request, f"Group '{name}' deleted successfully.")
        logger.info("Group deleted: %s by %s", name, request.user.email)
    except Exception as exc:
        logger.exception("Group delete failed: group_id=%s: %s", group_id, exc)
        messages.error(request, "Could not delete group. Please try again.")

    return redirect("library:admin_group_list")


# ===========================================================================
# Inline JSON — Author & Category creation from the book form modal
# ===========================================================================


@login_required
@require_permissions(P_VIEW_BOOK, P_CHANGE_BOOK, P_ADD_BOOK)
@require_POST
def author_create_json(request):
    """
    Called via fetch() from the book form modal.
    Returns {id, name} on success or {error} on failure.
    """
    name = request.POST.get("name", "").strip()
    if not name:
        return JsonResponse({"error": "Author name is required."}, status=400)
    if Author.objects.filter(name__iexact=name).exists():
        return JsonResponse({"error": f"Author '{escape(name)}' already exists."}, status=400)
    try:
        author = Author.objects.create(name=name)
        logger.info("Inline author created: %s by staff %s", author.name, request.user.email)
        return JsonResponse({"id": author.pk, "name": escape(author.name)})
    except Exception as exc:
        logger.exception("Inline author creation failed: %s", exc)
        return JsonResponse({"error": "Could not create author."}, status=500)


@login_required
@require_permissions(P_VIEW_BOOK, P_CHANGE_BOOK, P_ADD_BOOK)
@require_POST
def category_create_json(request):
    """
    Called via fetch() from the book form modal.
    Returns {id, name} on success or {error} on failure.
    """
    name = request.POST.get("name", "").strip()
    if not name:
        return JsonResponse({"error": "Category name is required."}, status=400)
    if Category.objects.filter(name__iexact=name).exists():
        return JsonResponse({"error": f"Category '{escape(name)}' already exists."}, status=400)
    try:
        category = Category.objects.create(name=name)
        logger.info("Inline category created: %s by staff %s", category.name, request.user.email)
        return JsonResponse({"id": category.pk, "name": escape(category.name)})
    except Exception as exc:
        logger.exception("Inline category creation failed: %s", exc)
        return JsonResponse({"error": "Could not create category."}, status=500)