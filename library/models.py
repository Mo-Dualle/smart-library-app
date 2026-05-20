import uuid
import datetime

from django.db import models
from django.contrib.auth.models import AbstractUser, Group, Permission
from django.contrib.contenttypes.models import ContentType


# ---------------------------------------------------------------------------
# Account (Custom User)
# ---------------------------------------------------------------------------

class Account(AbstractUser):
    """
    Custom user model that supports both members and librarian staff.
    Uses email as the primary login credential instead of username.
    """

    GENDER_CHOICES = [
        ("male",   "Male"),
        ("female", "Female"),
    ]

    email     = models.EmailField(unique=True)
    phone     = models.CharField(max_length=50)
    gender    = models.CharField(max_length=50, choices=GENDER_CHOICES, null=True, blank=True)
    is_member = models.BooleanField(default=False)
    avatar    = models.ImageField(upload_to="avatars/", default="avatars/avatar.jpg")

    USERNAME_FIELD  = "email"
    REQUIRED_FIELDS = ["username"]

    class Meta(AbstractUser.Meta):
        db_table = "account"
        verbose_name = "user"
        verbose_name_plural = "users"

    def __str__(self):
        return f"{self.get_full_name()} ({self.email})"


# ---------------------------------------------------------------------------
# Author
# ---------------------------------------------------------------------------

class Author(models.Model):
    """A book author."""

    name       = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "author"
        ordering = ["name"]

    def __str__(self):
        return self.name


# ---------------------------------------------------------------------------
# Category
# ---------------------------------------------------------------------------

class Category(models.Model):
    """Book genre / category (e.g. Fiction, Science, History)."""

    name       = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table  = "category"
        ordering  = ["name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


# ---------------------------------------------------------------------------
# Book
# ---------------------------------------------------------------------------

class Book(models.Model):
    """
    Represents a book title in the library catalog.
    `total_copies`     — physical copies owned by the library.
    `available_copies` — copies currently on the shelf and ready to borrow.
    """

    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title           = models.CharField(max_length=500)
    summary         = models.TextField(blank=True, default="")
    ISBN            = models.CharField(max_length=20, unique=True)
    publisher       = models.CharField(max_length=255)
    total_copies    = models.PositiveIntegerField(default=1)
    available_copies = models.PositiveIntegerField(default=1)
    image           = models.ImageField(upload_to="books/", default="books/default.jpg")
    created_at      = models.DateTimeField(auto_now_add=True)

    author   = models.ForeignKey(Author,   on_delete=models.RESTRICT, related_name="books")
    category = models.ForeignKey(Category, on_delete=models.RESTRICT, related_name="books")

    class Meta:
        db_table = "book"
        ordering = ["title"]

    def __str__(self):
        return f"{self.title} — {self.author}"

    @property
    def is_available(self):
        return self.available_copies > 0


# ---------------------------------------------------------------------------
# Borrow
# ---------------------------------------------------------------------------

class Borrow(models.Model):
    """
    Records a single borrow transaction between a member and a book.
    `has_fine` is set to True automatically when the book is returned late.
    """

    class Status(models.TextChoices):
        BORROWED = "borrowed", "Borrowed"
        RETURNED = "returned", "Returned"
        OVERDUE  = "overdue",  "Overdue"

    book       = models.ForeignKey(Book,    on_delete=models.RESTRICT, related_name="borrows")
    member     = models.ForeignKey(Account, on_delete=models.RESTRICT, related_name="borrows")
    quantity   = models.PositiveSmallIntegerField(default=1)
    status     = models.CharField(max_length=20, choices=Status.choices, default=Status.BORROWED)
    start_date = models.DateField()
    due_date   = models.DateField()
    return_date = models.DateField(null=True, blank=True)
    has_fine   = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "borrow"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.member} borrowed '{self.book}' ({self.status})"

    @property
    def is_overdue(self):
        if self.return_date:
            return self.return_date > self.due_date
        return datetime.date.today() > self.due_date


# ---------------------------------------------------------------------------
# Fine
# ---------------------------------------------------------------------------

class Fine(models.Model):
    """
    A financial penalty applied to a borrow record that was returned late.
    `amount_due` — total fine calculated.
    `amount_paid` — how much the member has paid so far.
    """

    borrow      = models.OneToOneField(Borrow,  on_delete=models.RESTRICT, related_name="fine")
    member      = models.ForeignKey(Account, on_delete=models.RESTRICT, related_name="fines")
    amount_due  = models.DecimalField(max_digits=8, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "fine"

    def __str__(self):
        return f"Fine for {self.member} — {self.amount_due} (paid: {self.amount_paid})"

    @property
    def is_settled(self):
        return self.amount_paid >= self.amount_due


# ---------------------------------------------------------------------------
# Reservation
# ---------------------------------------------------------------------------

class Reservation(models.Model):
    """
    Allows a member to queue for a book that currently has no available copies.
    When a copy becomes free, the oldest pending reservation should be fulfilled first.
    """

    class Status(models.TextChoices):
        PENDING   = "pending",   "Pending"
        FULFILLED = "fulfilled", "Fulfilled"
        CANCELLED = "cancelled", "Cancelled"

    book        = models.ForeignKey(Book,    on_delete=models.RESTRICT, related_name="reservations")
    member      = models.ForeignKey(Account, on_delete=models.RESTRICT, related_name="reservations")
    status      = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    reserved_on = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "reservation"
        ordering = ["reserved_on"]  # FIFO: oldest reservation served first

    def __str__(self):
        return f"{self.member} reserved '{self.book}' ({self.status})"


# ---------------------------------------------------------------------------
# Reading Session
# ---------------------------------------------------------------------------

class ReadingSession(models.Model):
    """
    Tracks in-library reading sessions (member sits and reads without borrowing).
    `time_in`  — when the member entered the reading area.
    `time_out` — when they left. Null if session is still active.
    """

    member   = models.ForeignKey(Account, on_delete=models.RESTRICT, related_name="reading_sessions")
    time_in  = models.DateTimeField()
    time_out = models.DateTimeField(null=True, blank=True)
    date     = models.DateField(auto_now_add=True)

    class Meta:
        db_table = "reading_session"
        ordering = ["-date", "-time_in"]

    def __str__(self):
        return f"{self.member} reading session on {self.date}"

    @property
    def is_active(self):
        return self.time_out is None

    @property
    def duration_minutes(self):
        if self.time_out:
            delta = self.time_out - self.time_in
            return round(delta.total_seconds() / 60)
        return None