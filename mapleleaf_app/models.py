"""Persistence for the website's lead, booking and proof workflows.

The models intentionally keep business rules flexible. Booking is a *request*
for a preferred drop-off window, not a guaranteed appointment, and photo
requests carry an explicit consent and retention date.
"""

import uuid
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone

from .content import SERVICE_BY_SLUG, SERVICES
from .estimating import money

ESTIMATE_SERVICE_CHOICES = [(service["slug"], service["title"]) for service in SERVICES]

ESTIMATE_DISCLAIMER = (
    "Planning estimate only — not a quote or guarantee. The final price depends on "
    "inspection, parts availability and hidden damage. MPI claims are settled by MPI, "
    "not by this number."
)


def _reference(prefix):
    stamp = timezone.now().strftime("%y%m%d")
    return f"{prefix}-{stamp}-{uuid.uuid4().hex[:5].upper()}"


def _blog_image_path(instance, filename):
    stem = Path(filename).stem[:60] or "blog"
    return f"blog/{timezone.now():%Y/%m/%d}/{stem}.webp"


class ReferenceModel(models.Model):
    reference = models.CharField(max_length=24, unique=True, editable=False, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    REFERENCE_PREFIX = "ML"

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = _reference(self.REFERENCE_PREFIX)
        super().save(*args, **kwargs)


class CallbackRequest(ReferenceModel):
    REFERENCE_PREFIX = "CB"

    STATUS_NEW = "new"
    STATUS_CONTACTED = "contacted"
    STATUS_BOOKED = "booked"
    STATUS_CLOSED = "closed"
    STATUS_CHOICES = [
        (STATUS_NEW, "New"),
        (STATUS_CONTACTED, "Contacted"),
        (STATUS_BOOKED, "Booked"),
        (STATUS_CLOSED, "Closed"),
    ]

    full_name = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=40)
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="callback_requests",
    )
    preferred_time = models.CharField(max_length=60)
    service_needed = models.CharField(max_length=140)
    vehicle_description = models.TextField(blank=True)
    source_page = models.CharField(max_length=160, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_NEW)
    internal_notes = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Callback request"

    def __str__(self):
        return f"{self.reference} · {self.full_name}"


class ClaimIntake(ReferenceModel):
    REFERENCE_PREFIX = "CL"

    STATUS_NEW = "new"
    STATUS_REVIEWED = "reviewed"
    STATUS_CLOSED = "closed"
    STATUS_CHOICES = [
        (STATUS_NEW, "New"),
        (STATUS_REVIEWED, "Reviewed"),
        (STATUS_CLOSED, "Closed"),
    ]

    full_name = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=40)
    email = models.EmailField(blank=True)
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="claim_intakes",
    )
    claim_number = models.CharField(max_length=60, blank=True)
    has_claim = models.CharField(max_length=20, blank=True)
    anyone_injured = models.CharField(max_length=10, blank=True)
    vehicle_drivable = models.CharField(max_length=10, blank=True)
    registered_owner = models.CharField(max_length=10, blank=True)
    damage_description = models.TextField(blank=True)
    preferred_time = models.CharField(max_length=60, blank=True)
    result_summary = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_NEW)
    internal_notes = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "MPI claim intake"

    def __str__(self):
        return f"{self.reference} · {self.full_name}"


class BookingRequest(ReferenceModel):
    REFERENCE_PREFIX = "BK"

    STATUS_NEW = "new"
    STATUS_CONFIRMED = "confirmed"
    STATUS_DECLINED = "declined"
    STATUS_COMPLETED = "completed"
    STATUS_CHOICES = [
        (STATUS_NEW, "New request"),
        (STATUS_CONFIRMED, "Confirmed by shop"),
        (STATUS_DECLINED, "Declined"),
        (STATUS_COMPLETED, "Completed"),
    ]

    DROP_OFF = "drop_off"
    WAIT = "wait"
    VISIT_CHOICES = [
        (DROP_OFF, "Drop off the vehicle"),
        (WAIT, "Wait at the shop"),
    ]

    full_name = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=40)
    email = models.EmailField(blank=True)
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="booking_requests",
    )
    vehicle = models.CharField(max_length=160)
    service = models.CharField(max_length=140)
    preferred_date = models.DateField()
    preferred_window = models.CharField(max_length=60)
    visit_type = models.CharField(max_length=20, choices=VISIT_CHOICES, default=DROP_OFF)
    notes = models.TextField(blank=True)
    privacy_consent = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_NEW)
    internal_notes = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Booking request"

    def __str__(self):
        return f"{self.reference} · {self.full_name} · {self.preferred_date}"


def photo_upload_path(instance, filename):
    today = timezone.localdate()
    safe_name = "".join(ch for ch in filename if ch.isalnum() or ch in ("-", "_", "."))[-80:]
    return f"photo-requests/{today:%Y/%m}/{uuid.uuid4().hex[:8]}-{safe_name}"


class PhotoRequest(ReferenceModel):
    REFERENCE_PREFIX = "PH"

    STATUS_NEW = "new"
    STATUS_REVIEWED = "reviewed"
    STATUS_QUOTED = "quoted"
    STATUS_CLOSED = "closed"
    STATUS_CHOICES = [
        (STATUS_NEW, "New"),
        (STATUS_REVIEWED, "Reviewed"),
        (STATUS_QUOTED, "Quoted"),
        (STATUS_CLOSED, "Closed"),
    ]

    full_name = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=40)
    email = models.EmailField(blank=True)
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="photo_requests",
    )
    vehicle = models.CharField(max_length=160)
    damage_type = models.CharField(max_length=80)
    description = models.TextField(blank=True)
    preferred_time = models.CharField(max_length=60, blank=True)
    privacy_consent = models.BooleanField(default=False)
    retention_expires_at = models.DateField(blank=True, null=True, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_NEW)
    internal_notes = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Photo request"

    def __str__(self):
        return f"{self.reference} · {self.full_name}"

    @property
    def retention_days(self):
        return getattr(settings, "PHOTO_RETENTION_DAYS", 365)

    def set_retention(self):
        self.retention_expires_at = timezone.localdate() + timedelta(days=self.retention_days)

    @property
    def is_expired(self):
        return bool(self.retention_expires_at and self.retention_expires_at < timezone.localdate())


class PhotoRequestImage(models.Model):
    request = models.ForeignKey(PhotoRequest, related_name="photos", on_delete=models.CASCADE)
    image = models.ImageField(upload_to=photo_upload_path)
    caption = models.CharField(max_length=160, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["uploaded_at"]
        verbose_name = "Photo request image"

    def __str__(self):
        return f"{self.request.reference} photo {self.pk}"


class RepairStory(models.Model):
    """A permissioned before/after repair story.

    Stories only appear publicly when ``customer_permission`` and
    ``is_published`` are both true. There is deliberately no seed data.
    """

    title = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180, unique=True)
    category = models.CharField(max_length=40, choices=[("body", "Body & glass"), ("mechanical", "Mechanical"), ("maintenance", "Maintenance")])
    vehicle = models.CharField(max_length=120, blank=True)
    summary = models.TextField()
    work_done = models.TextField(blank=True)
    before_image = models.ImageField(upload_to="repair-stories/before/")
    after_image = models.ImageField(upload_to="repair-stories/after/")
    completed_on = models.DateField(blank=True, null=True)
    customer_permission = models.BooleanField(
        default=False,
        help_text="The customer has given written permission to publish these photos.",
    )
    is_published = models.BooleanField(default=False)
    display_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["display_order", "-completed_on", "-created_at"]
        verbose_name = "Repair story"

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("repair_stories") + f"#story-{self.slug}"

    @property
    def is_public(self):
        return self.is_published and self.customer_permission


class StaffProfile(models.Model):
    """Workspace role for a signed-in shop account.

    Masters run the site and assign work. Employees can only see and update
    the tickets assigned to them. The role lives in its own table so an
    employee never needs Django staff or admin access.
    """

    ROLE_MASTER = "master"
    ROLE_EMPLOYEE = "employee"
    ROLE_CHOICES = [
        (ROLE_MASTER, "Master"),
        (ROLE_EMPLOYEE, "Employee"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="staff_profile",
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_EMPLOYEE)
    phone = models.CharField(max_length=40, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user__first_name", "user__last_name", "user__username"]
        verbose_name = "Staff profile"

    def __str__(self):
        return f"{self.user.get_username()} · {self.get_role_display()}"

    @property
    def is_master(self):
        return self.role == self.ROLE_MASTER

    @property
    def is_employee(self):
        return self.role == self.ROLE_EMPLOYEE


class CustomerProfile(models.Model):
    """A customer account created by the shop.

    Customer accounts are deliberately separate from staff profiles. They can
    sign in to see only the requests linked to their own account. There is no
    public sign-up; the shop creates the account and shares the sign-in
    details directly.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="customer_profile",
    )
    phone = models.CharField(max_length=40, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user__first_name", "user__last_name", "user__username"]
        verbose_name = "Customer account"

    def __str__(self):
        return self.user.get_full_name() or self.user.get_username()


class WorkTicket(ReferenceModel):
    """A job the master assigns to one employee."""

    REFERENCE_PREFIX = "WT"

    STATUS_ASSIGNED = "assigned"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_COMPLETED = "completed"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_ASSIGNED, "Assigned"),
        (STATUS_IN_PROGRESS, "In progress"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_CANCELLED, "Cancelled"),
    ]
    OPEN_STATUSES = (STATUS_ASSIGNED, STATUS_IN_PROGRESS)

    work_type = models.CharField(max_length=140)
    vehicle = models.CharField(max_length=160)
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="work_tickets",
    )
    booking = models.ForeignKey(
        BookingRequest,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="work_tickets",
    )
    customer_name = models.CharField(max_length=100, blank=True)
    customer_phone = models.CharField(max_length=40, blank=True)
    instructions = models.TextField(blank=True)
    employee_notes = models.TextField(blank=True)
    due_date = models.DateField(null=True, blank=True, db_index=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_ASSIGNED,
        db_index=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_work_tickets",
    )
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Work ticket"

    def __str__(self):
        return f"{self.reference} · {self.work_type} · {self.vehicle}"

    @property
    def is_open(self):
        return self.status in self.OPEN_STATUSES

    @property
    def is_overdue(self):
        return bool(
            self.due_date
            and self.is_open
            and self.due_date < timezone.localdate()
        )


class Supplier(models.Model):
    """A parts supplier used to group the reorder list."""

    name = models.CharField(max_length=120, unique=True)
    contact_name = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    account_number = models.CharField(max_length=80, blank=True)
    lead_time_days = models.PositiveSmallIntegerField(
        default=2,
        help_text="Typical days from placing an order to the part being on the shelf.",
    )
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Supplier"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self.name = (self.name or "").strip()
        super().save(*args, **kwargs)


class Part(models.Model):
    """A stockroom item with a bin, a reorder level and a running balance.

    ``quantity_on_hand`` is a cached balance. It is only written by
    ``inventory.record_movement``, which also writes the immutable ledger row.
    """

    CATEGORY_BODY = "body"
    CATEGORY_GLASS = "glass"
    CATEGORY_PAINT = "paint"
    CATEGORY_FASTENERS = "fasteners"
    CATEGORY_FLUIDS = "fluids"
    CATEGORY_CONSUMABLES = "consumables"
    CATEGORY_TOOLS = "tools"
    CATEGORY_OTHER = "other"
    CATEGORY_CHOICES = [
        (CATEGORY_BODY, "Body panels"),
        (CATEGORY_GLASS, "Glass"),
        (CATEGORY_PAINT, "Paint & supplies"),
        (CATEGORY_FASTENERS, "Fasteners & clips"),
        (CATEGORY_FLUIDS, "Fluids"),
        (CATEGORY_CONSUMABLES, "Shop consumables"),
        (CATEGORY_TOOLS, "Tools"),
        (CATEGORY_OTHER, "Other"),
    ]

    UNIT_EACH = "each"
    UNIT_PAIR = "pair"
    UNIT_SET = "set"
    UNIT_LITRE = "litre"
    UNIT_PINT = "pint"
    UNIT_QUART = "quart"
    UNIT_GALLON = "gallon"
    UNIT_ROLL = "roll"
    UNIT_BOX = "box"
    UNIT_PACK = "pack"
    UNIT_CHOICES = [
        (UNIT_EACH, "Each"),
        (UNIT_PAIR, "Pair"),
        (UNIT_SET, "Set"),
        (UNIT_LITRE, "Litre"),
        (UNIT_PINT, "Pint"),
        (UNIT_QUART, "Quart"),
        (UNIT_GALLON, "Gallon"),
        (UNIT_ROLL, "Roll"),
        (UNIT_BOX, "Box"),
        (UNIT_PACK, "Pack"),
    ]

    sku = models.CharField(
        max_length=40,
        unique=True,
        help_text="A short shop code. Also used for scanner and search lookups.",
    )
    name = models.CharField(max_length=160)
    category = models.CharField(
        max_length=40,
        choices=CATEGORY_CHOICES,
        default=CATEGORY_OTHER,
    )
    brand = models.CharField(max_length=80, blank=True)
    part_number = models.CharField(max_length=80, blank=True, db_index=True)
    barcode = models.CharField(max_length=80, blank=True, db_index=True)
    bin_location = models.CharField(
        max_length=40,
        blank=True,
        db_index=True,
        help_text="Shelf label, for example A-02-3.",
    )
    unit = models.CharField(max_length=20, choices=UNIT_CHOICES, default=UNIT_EACH)
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="parts",
    )
    cost_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    quantity_on_hand = models.IntegerField(default=0, editable=False)
    reorder_level = models.PositiveIntegerField(
        default=0,
        help_text="Reorder when at or below this quantity. Leave at 0 for items that are not tracked.",
    )
    reorder_target = models.PositiveIntegerField(
        default=0,
        help_text="Restock up to this quantity. Must be at least the reorder level.",
    )
    is_critical = models.BooleanField(
        default=False,
        help_text="Pinned to the top of the reorder list. Use for parts that stop a job.",
    )
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    last_counted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Part"
        verbose_name_plural = "Parts"

    def __str__(self):
        return f"{self.sku} · {self.name}"

    def clean(self):
        super().clean()
        if self.reorder_level and not self.reorder_target:
            raise ValidationError(
                {"reorder_target": "Set a restock target when a reorder level is set."}
            )
        if self.reorder_target and self.reorder_target < self.reorder_level:
            raise ValidationError(
                {"reorder_target": "The restock target must be at least the reorder level."}
            )
        if self.cost_price is not None and self.cost_price < 0:
            raise ValidationError({"cost_price": "Cost cannot be negative."})

    def save(self, *args, **kwargs):
        self.sku = (self.sku or "").strip().upper()
        self.bin_location = (self.bin_location or "").strip().upper()
        self.barcode = (self.barcode or "").strip()
        self.part_number = (self.part_number or "").strip().upper()
        super().save(*args, **kwargs)

    @property
    def is_low_stock(self):
        return bool(
            self.is_active
            and self.reorder_level > 0
            and self.quantity_on_hand <= self.reorder_level
        )

    @property
    def is_out_of_stock(self):
        return bool(self.is_active and self.quantity_on_hand <= 0)

    @property
    def suggested_order_quantity(self):
        if not self.is_low_stock:
            return 0
        target = self.reorder_target
        if target <= self.reorder_level:
            target = self.reorder_level + 1
        return max(target - self.quantity_on_hand, 1)

    @property
    def suggested_order_cost(self):
        return self.suggested_order_quantity * (self.cost_price or Decimal("0.00"))

    @property
    def stock_status_label(self):
        if not self.is_active:
            return "Archived"
        if self.quantity_on_hand <= 0:
            return "Out of stock"
        if self.is_low_stock:
            return "Reorder"
        return "In stock"

    @property
    def stock_status_class(self):
        if not self.is_active:
            return "is-muted"
        if self.quantity_on_hand <= 0:
            return "is-bad"
        if self.is_low_stock:
            return "is-warn"
        return "is-good"

    @property
    def stock_value(self):
        return (self.cost_price or Decimal("0.00")) * self.quantity_on_hand


class StockMovement(models.Model):
    """Append-only record of every stock change.

    Movements are never edited or deleted. A correction is a new movement with
    a reason, so the shelf history always explains the current balance.
    """

    KIND_RECEIVE = "receive"
    KIND_USE = "use"
    KIND_RETURN = "return"
    KIND_COUNT = "count"
    KIND_ADJUST = "adjust"
    KIND_CHOICES = [
        (KIND_RECEIVE, "Received"),
        (KIND_USE, "Used"),
        (KIND_RETURN, "Returned"),
        (KIND_COUNT, "Counted"),
        (KIND_ADJUST, "Adjusted"),
    ]

    part = models.ForeignKey(
        Part,
        on_delete=models.PROTECT,
        related_name="movements",
    )
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, db_index=True)
    quantity_delta = models.IntegerField(
        help_text="Signed change: positive adds stock, negative removes it."
    )
    balance_after = models.IntegerField()
    unit_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    work_ticket = models.ForeignKey(
        WorkTicket,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="part_movements",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_movements",
    )
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "Stock movement"
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(quantity_delta=0),
                name="stock_movement_nonzero_delta",
            )
        ]

    def __str__(self):
        return f"{self.part.sku} · {self.get_kind_display()} {self.quantity_delta:+d}"


class Review(models.Model):
    author = models.CharField(max_length=100)
    quote = models.TextField()
    rating = models.PositiveSmallIntegerField(default=5)
    category = models.CharField(max_length=40, default="quick")
    category_label = models.CharField(max_length=60, default="Customer feedback")
    source_label = models.CharField(max_length=80, default="Customer feedback")
    is_published = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["display_order", "created_at"]
        verbose_name = "Review"

    def __str__(self):
        return f"{self.author} · {self.rating}/5"


class EstimateService(models.Model):
    """A master-owned price basis for one public service.

    The estimator never invents a number. A service is only shown with a price
    when the shop owner has entered a base price and switched it on. The range
    visitors see is ``base_price ± spread_percent``, adjusted by the vehicle
    and severity multipliers on :class:`EstimateSettings`.
    """

    slug = models.CharField(
        max_length=40,
        unique=True,
        choices=ESTIMATE_SERVICE_CHOICES,
        help_text="The public service this price belongs to.",
    )
    enabled = models.BooleanField(
        default=False,
        help_text="Show a price range for this service on the public estimator.",
    )
    base_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Typical price before vehicle and severity adjustments. Leave blank until the shop has a number.",
    )
    spread_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("20.00"),
        help_text="How far the range reaches either side of the base price. 20 gives −20% to +20%.",
    )
    unit_label = models.CharField(
        max_length=60,
        default="per job",
        help_text="Plain wording shown beside the range, for example ‘per panel’ or ‘per axle’.",
    )
    uses_severity = models.BooleanField(
        default=False,
        help_text="Ask about minor, moderate or severe damage. Use this for body and paint work.",
    )
    display_order = models.PositiveIntegerField(default=0)
    notes = models.TextField(
        blank=True,
        help_text="Internal reminder about how this price was set. Never shown publicly.",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_estimates",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["display_order", "slug"]
        verbose_name = "Estimate service"
        verbose_name_plural = "Estimate services"

    def __str__(self):
        return self.title

    def clean(self):
        super().clean()
        if self.base_price is not None and self.base_price < 0:
            raise ValidationError({"base_price": "The base price cannot be negative."})
        if self.spread_percent is not None and not 0 <= self.spread_percent < 100:
            raise ValidationError({"spread_percent": "Choose a spread from 0% to 99%."})
        if self.enabled and self.base_price is None:
            raise ValidationError(
                {"base_price": "Enter a base price before turning this estimate on."}
            )

    @property
    def content(self):
        return SERVICE_BY_SLUG.get(self.slug, {})

    @property
    def title(self):
        return self.content.get("title") or self.slug.replace("-", " ").title()

    @property
    def short_title(self):
        return self.content.get("short_title") or self.title

    @property
    def summary(self):
        return self.content.get("summary", "")

    @property
    def icon(self):
        return self.content.get("material_icon", "request_quote")

    @property
    def is_priced(self):
        return bool(self.enabled and self.base_price is not None and self.base_price > 0)

    @property
    def range_low(self):
        if self.base_price is None:
            return None
        spread = (self.spread_percent or Decimal("0")) / Decimal("100")
        return self.base_price * (1 - spread)

    @property
    def range_high(self):
        if self.base_price is None:
            return None
        spread = (self.spread_percent or Decimal("0")) / Decimal("100")
        return self.base_price * (1 + spread)

    @property
    def range_display(self):
        if self.range_low is None or self.range_high is None:
            return "Not priced yet"
        return f"{money(self.range_low)} – {money(self.range_high)}"


class EstimateAddOn(models.Model):
    """A fixed extra the visitor can add to one estimate service."""

    service = models.ForeignKey(
        EstimateService,
        on_delete=models.CASCADE,
        related_name="addons",
    )
    label = models.CharField(max_length=120)
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="A flat amount added to both ends of the range.",
    )
    enabled = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "label"]
        verbose_name = "Estimate add-on"
        verbose_name_plural = "Estimate add-ons"

    def __str__(self):
        return f"{self.label} (+{money(self.amount)})"

    def clean(self):
        super().clean()
        if self.amount is not None and self.amount < 0:
            raise ValidationError({"amount": "An add-on cannot be negative."})


class EstimateSettings(models.Model):
    """Single-row public estimator configuration.

    Kept separate from the service rows so the shop owner can switch the whole
    tool off, change the rounding step or adjust the vehicle/severity
    multipliers without touching each service.
    """

    ROUNDING_CHOICES = [
        (1, "$1"),
        (5, "$5"),
        (10, "$10"),
        (25, "$25"),
        (50, "$50"),
    ]

    site_enabled = models.BooleanField(
        default=False,
        help_text="Master switch. The public estimator shows prices only when this is on.",
    )
    rounding_step = models.PositiveSmallIntegerField(
        choices=ROUNDING_CHOICES,
        default=5,
        help_text="Round the low end down and the high end up to this step.",
    )
    car_multiplier = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("1.00"),
        help_text="Car or small SUV adjustment.",
    )
    suv_multiplier = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("1.15"),
        help_text="SUV, van or pickup adjustment.",
    )
    luxury_multiplier = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("1.40"),
        help_text="Luxury or premium vehicle adjustment.",
    )
    severity_minor = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("1.00"),
        help_text="Minor damage adjustment. Only used by services that ask about severity.",
    )
    severity_moderate = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("1.30"),
        help_text="Moderate damage adjustment.",
    )
    severity_severe = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("1.75"),
        help_text="Severe damage adjustment.",
    )
    prices_updated_on = models.DateField(
        null=True,
        blank=True,
        help_text="Shown to visitors beside the range. Leave blank to hide the date.",
    )
    disclaimer = models.TextField(default=ESTIMATE_DISCLAIMER)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_estimate_settings",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Estimator settings"
        verbose_name_plural = "Estimator settings"

    def __str__(self):
        return "Estimator settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj = cls.objects.filter(pk=1).first()
        if obj is None:
            obj = cls.objects.create(pk=1)
        return obj


class AnalyticsEvent(models.Model):
    name = models.CharField(max_length=80, db_index=True)
    path = models.CharField(max_length=300, blank=True)
    page_title = models.CharField(max_length=200, blank=True)
    referrer = models.CharField(max_length=500, blank=True)
    session_key = models.CharField(max_length=64, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Analytics event"

    def __str__(self):
        return f"{self.name} · {self.created_at:%Y-%m-%d %H:%M}"


class BlogCategory(models.Model):
    """A public grouping for articles, managed by the master account."""

    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Blog category"
        verbose_name_plural = "Blog categories"

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("blog_category", kwargs={"slug": self.slug})

    def save(self, *args, **kwargs):
        self.name = (self.name or "").strip()
        super().save(*args, **kwargs)


class BlogTag(models.Model):
    """A reusable label for cross-linking related articles."""

    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Blog tag"
        verbose_name_plural = "Blog tags"

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("blog_tag", kwargs={"slug": self.slug})

    def save(self, *args, **kwargs):
        self.name = (self.name or "").strip()
        super().save(*args, **kwargs)


class BlogPost(models.Model):
    """A master-authored Markdown article with an enforced publish gate.

    Drafts stay private. Only ``published`` posts appear in the public blog,
    sitemap and structured data. The SEO checklist is evaluated before a post
    can move from draft to published; see ``mapleleaf_app.blog``.
    """

    STATUS_DRAFT = "draft"
    STATUS_PUBLISHED = "published"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_PUBLISHED, "Published"),
    ]

    title = models.CharField(max_length=180, unique=True)
    slug = models.SlugField(max_length=200, unique=True)
    excerpt = models.TextField(blank=True)
    body = models.TextField(
        help_text="Markdown only. Raw HTML is removed when the article is rendered.",
    )
    focus_keyword = models.CharField(max_length=80, blank=True)
    seo_title = models.CharField(max_length=120, blank=True)
    meta_description = models.TextField(blank=True)
    status = models.CharField(
        max_length=12,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
        db_index=True,
    )
    category = models.ForeignKey(
        BlogCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="posts",
    )
    tags = models.ManyToManyField(BlogTag, blank=True, related_name="posts")
    featured_image = models.ImageField(upload_to=_blog_image_path, blank=True)
    featured_image_alt = models.CharField(max_length=180, blank=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="blog_posts",
    )
    allow_comments = models.BooleanField(default=True)
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-published_at", "-created_at"]
        verbose_name = "Blog post"
        verbose_name_plural = "Blog posts"
        indexes = [
            models.Index(fields=["status", "published_at"]),
        ]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("blog_post", kwargs={"slug": self.slug})

    @property
    def is_published(self):
        return self.status == self.STATUS_PUBLISHED

    @property
    def display_title(self):
        return (self.seo_title or self.title).strip()

    @property
    def display_description(self):
        return (self.meta_description or self.excerpt).strip()

    @property
    def word_count(self):
        return len((self.body or "").split())

    @property
    def reading_time_minutes(self):
        return max(1, (self.word_count + 219) // 220)


class BlogComment(models.Model):
    """An instant public comment. Hidden comments never reach the article page."""

    post = models.ForeignKey(BlogPost, on_delete=models.CASCADE, related_name="comments")
    name = models.CharField(max_length=100)
    body = models.TextField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    is_hidden = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "Blog comment"
        verbose_name_plural = "Blog comments"

    def __str__(self):
        return f"{self.name} on {self.post.title}"
