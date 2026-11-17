"""Forms used by the staff management area.

These forms only handle shop-side edits. Public-facing validation lives in
``forms.py`` so visitor rules and staff rules cannot accidentally drift.
"""

from __future__ import annotations

from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordChangeForm,
    SetPasswordForm,
    UserCreationForm,
)
from django.core.exceptions import ValidationError
from django.core.files.images import get_image_dimensions
from django.core.files.uploadedfile import UploadedFile
from django.utils.text import slugify

from .forms import StyledFormMixin, _apply_field_styles, validate_phone
from .images import optimize_photo_upload
from .models import (
    BookingRequest,
    CallbackRequest,
    ClaimIntake,
    EstimateAddOn,
    EstimateService,
    EstimateSettings,
    Part,
    PhotoRequest,
    RepairStory,
    Review,
    StaffProfile,
    Supplier,
    WorkTicket,
)
from .roles import employee_users

STORY_IMAGE_MAX_BYTES = 12 * 1024 * 1024
STORY_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
STORY_IMAGE_MAX_DIMENSION = 1800
STORY_IMAGE_QUALITY = 84


class StaffFormMixin(StyledFormMixin):
    """Apply the public field styling to staff forms as well."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_field_styles(self)


class StaffAuthenticationForm(AuthenticationForm):
    username = forms.CharField(
        label="Username",
        widget=forms.TextInput(
            attrs={
                "class": "field",
                "autocomplete": "username",
                "placeholder": "Your username",
                "autofocus": True,
            }
        ),
    )
    password = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "class": "field",
                "autocomplete": "current-password",
                "placeholder": "Your password",
            }
        ),
    )

    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "That username and password did not match. Please try again.",
    }

    def confirm_login_allowed(self, user):
        # Both masters and employees use this form. Whether the account has a
        # workspace role is checked by the login view after authentication.
        super().confirm_login_allowed(user)


class StaffPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_field_styles(self)


class StaffProfileForm(StaffFormMixin, forms.ModelForm):
    phone = forms.CharField(
        max_length=40,
        required=False,
        label="Phone number",
        help_text="Optional. Shown to the master if they need to reach you.",
    )

    class Meta:
        model = get_user_model()
        fields = ("first_name", "last_name", "email")
        labels = {
            "first_name": "First name",
            "last_name": "Last name",
            "email": "Email address",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        profile = getattr(self.instance, "staff_profile", None)
        if profile:
            self.fields["phone"].initial = profile.phone

    def clean_phone(self):
        value = (self.cleaned_data.get("phone") or "").strip()
        if value:
            validate_phone(value)
        return value

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            default_role = (
                StaffProfile.ROLE_MASTER
                if user.is_superuser or user.is_staff
                else StaffProfile.ROLE_EMPLOYEE
            )
            profile, _created = StaffProfile.objects.get_or_create(
                user=user,
                defaults={"role": default_role},
            )
            profile.phone = self.cleaned_data.get("phone", "")
            profile.save(update_fields=["phone", "updated_at"])
        return user


def _clean_optional_phone(value):
    value = (value or "").strip()
    if value:
        validate_phone(value)
    return value


class EmployeeCreateForm(UserCreationForm):
    first_name = forms.CharField(max_length=150, label="First name")
    last_name = forms.CharField(max_length=150, label="Last name")
    email = forms.EmailField(max_length=254, required=False, label="Email address")
    phone = forms.CharField(max_length=40, required=False, label="Phone number")

    class Meta:
        model = get_user_model()
        fields = ("username", "first_name", "last_name", "email")
        labels = {"username": "Sign-in username"}
        help_texts = {
            "username": "Letters, digits and @/./+/-/_ only. The employee uses this to sign in.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_field_styles(self)
        self.fields["username"].widget.attrs["placeholder"] = "e.g. jordan"
        self.fields["first_name"].widget.attrs["placeholder"] = "Jordan"
        self.fields["last_name"].widget.attrs["placeholder"] = "Lee"
        self.fields["email"].widget.attrs["placeholder"] = "Optional"
        self.fields["phone"].widget.attrs["placeholder"] = "Optional"

    def clean_phone(self):
        return _clean_optional_phone(self.cleaned_data.get("phone"))

    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_staff = False
        user.is_superuser = False
        if commit:
            user.save()
            StaffProfile.objects.create(
                user=user,
                role=StaffProfile.ROLE_EMPLOYEE,
                phone=self.cleaned_data.get("phone", ""),
            )
        return user


class EmployeeSetPasswordForm(SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_field_styles(self)


class WorkTicketForm(StaffFormMixin, forms.ModelForm):
    class Meta:
        model = WorkTicket
        fields = (
            "work_type",
            "vehicle",
            "assignee",
            "customer_name",
            "customer_phone",
            "due_date",
            "instructions",
        )
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "instructions": forms.Textarea(
                attrs={
                    "rows": 5,
                    "placeholder": "What needs doing, what to check first, or anything the employee must know.",
                }
            ),
        }
        labels = {
            "work_type": "Type of work",
            "vehicle": "Vehicle (year, make, model, colour)",
            "assignee": "Assign to",
            "customer_name": "Customer name",
            "customer_phone": "Customer phone",
            "due_date": "Due date",
            "instructions": "Instructions for the employee",
        }
        help_texts = {
            "vehicle": "For example: 2019 Honda Civic, silver, plate ABC 123.",
            "assignee": "Only active employee accounts are listed. Add employees on the Team page.",
            "customer_name": "Optional. The employee can see this while working on the ticket.",
            "customer_phone": "Optional. Shown to the assigned employee only.",
            "due_date": "Optional. Overdue tickets are highlighted on the work board.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assignee"].queryset = employee_users()
        self.fields["assignee"].empty_label = "Choose an employee"
        self.fields["assignee"].label_from_instance = (
            lambda user: user.get_full_name() or user.get_username()
        )

    def clean_customer_phone(self):
        return _clean_optional_phone(self.cleaned_data.get("customer_phone"))

    def clean_assignee(self):
        assignee = self.cleaned_data.get("assignee")
        profile = getattr(assignee, "staff_profile", None)
        if not profile or profile.role != StaffProfile.ROLE_EMPLOYEE:
            raise ValidationError("Choose an active employee account.")
        return assignee


class WorkTicketNoteForm(StaffFormMixin, forms.ModelForm):
    class Meta:
        model = WorkTicket
        fields = ("employee_notes",)
        widgets = {
            "employee_notes": forms.Textarea(
                attrs={
                    "rows": 5,
                    "placeholder": "What you found, what you did, or what is still needed.",
                }
            )
        }
        labels = {"employee_notes": "Work notes"}


class CallbackUpdateForm(StaffFormMixin, forms.ModelForm):
    class Meta:
        model = CallbackRequest
        fields = ("status", "internal_notes")
        widgets = {"internal_notes": forms.Textarea(attrs={"rows": 5, "placeholder": "Notes only the shop can see."})}


class BookingUpdateForm(StaffFormMixin, forms.ModelForm):
    class Meta:
        model = BookingRequest
        fields = ("status", "internal_notes")
        widgets = {"internal_notes": forms.Textarea(attrs={"rows": 5, "placeholder": "Notes only the shop can see."})}


class ClaimUpdateForm(StaffFormMixin, forms.ModelForm):
    class Meta:
        model = ClaimIntake
        fields = ("status", "internal_notes")
        widgets = {"internal_notes": forms.Textarea(attrs={"rows": 5, "placeholder": "Notes only the shop can see."})}


class PhotoUpdateForm(StaffFormMixin, forms.ModelForm):
    class Meta:
        model = PhotoRequest
        fields = ("status", "internal_notes")
        widgets = {"internal_notes": forms.Textarea(attrs={"rows": 5, "placeholder": "Notes only the shop can see."})}


class ReviewForm(StaffFormMixin, forms.ModelForm):
    category = forms.ChoiceField(
        choices=[("body", "Body work"), ("quick", "Quick service")],
        label="Review category",
    )
    rating = forms.ChoiceField(
        choices=[(i, f"{i} star{'s' if i != 1 else ''}") for i in range(5, 0, -1)],
        label="Rating",
    )

    class Meta:
        model = Review
        fields = (
            "author",
            "quote",
            "rating",
            "category",
            "category_label",
            "source_label",
            "is_published",
            "display_order",
        )
        widgets = {
            "quote": forms.Textarea(attrs={"rows": 4, "placeholder": "The customer's words, exactly as shared."}),
            "category_label": forms.TextInput(attrs={"placeholder": "Body work"}),
            "source_label": forms.TextInput(attrs={"placeholder": "Customer feedback"}),
        }
        labels = {
            "author": "Customer name",
            "quote": "Review",
            "category_label": "Category label on the website",
            "source_label": "Source label",
            "is_published": "Show this review on the website",
            "display_order": "Display order",
        }

    def clean(self):
        cleaned = super().clean()
        category = cleaned.get("category")
        label = (cleaned.get("category_label") or "").strip()
        if category and not label:
            cleaned["category_label"] = dict(self.fields["category"].choices).get(category, "Customer feedback")
        if not (cleaned.get("source_label") or "").strip():
            cleaned["source_label"] = "Customer feedback"
        return cleaned


class RepairStoryForm(StaffFormMixin, forms.ModelForm):
    slug = forms.SlugField(required=False, label="Web address slug")

    class Meta:
        model = RepairStory
        fields = (
            "title",
            "slug",
            "category",
            "vehicle",
            "summary",
            "work_done",
            "before_image",
            "after_image",
            "completed_on",
            "customer_permission",
            "is_published",
            "display_order",
        )
        widgets = {
            "summary": forms.Textarea(attrs={"rows": 3, "placeholder": "What happened and what the customer asked for."}),
            "work_done": forms.Textarea(attrs={"rows": 3, "placeholder": "What the shop repaired or replaced."}),
            "completed_on": forms.DateInput(attrs={"type": "date"}),
        }
        labels = {
            "title": "Story title",
            "slug": "Web address slug",
            "vehicle": "Vehicle (year, make, model)",
            "summary": "Short summary",
            "work_done": "Work completed",
            "before_image": "Before photo",
            "after_image": "After photo",
            "completed_on": "Completed on",
            "customer_permission": "The customer gave written permission to publish these photos",
            "is_published": "Publish this story on the website",
            "display_order": "Display order",
        }
        help_texts = {
            "slug": "Leave blank and we will build it from the title.",
            "customer_permission": "Do not tick this until the written permission is on file.",
            "is_published": "The story only appears publicly when permission and publish are both ticked.",
        }

    def clean_slug(self):
        slug = (self.cleaned_data.get("slug") or "").strip()
        if not slug:
            slug = slugify(self.cleaned_data.get("title") or "")
        if not slug:
            raise ValidationError("Add a title or a slug so the story has a web address.")
        existing = RepairStory.objects.exclude(pk=self.instance.pk).filter(slug=slug)
        if existing.exists():
            raise ValidationError("Another story already uses that slug. Choose a different one.")
        return slug

    def _clean_story_image(self, field_name):
        upload = self.cleaned_data.get(field_name)
        if not isinstance(upload, UploadedFile):
            return upload

        if upload.size > STORY_IMAGE_MAX_BYTES:
            raise ValidationError(f"Each photo must be smaller than {STORY_IMAGE_MAX_BYTES // (1024 * 1024)} MB.")
        content_type = getattr(upload, "content_type", "").lower()
        if content_type and content_type not in STORY_IMAGE_TYPES:
            raise ValidationError("Please upload a JPEG, PNG or WebP image.")
        try:
            width, height = get_image_dimensions(upload)
        except Exception:
            raise ValidationError("That file does not look like a readable image.")
        if not width or not height:
            raise ValidationError("That image could not be read. Please try another file.")
        if width > 6000 or height > 6000:
            raise ValidationError("That image is too large in pixel dimensions. Please resize it and try again.")
        upload.seek(0)
        try:
            return optimize_photo_upload(
                upload,
                max_dimension=STORY_IMAGE_MAX_DIMENSION,
                quality=STORY_IMAGE_QUALITY,
            )
        except Exception:
            raise ValidationError("That image could not be prepared. Please try a different JPEG, PNG or WebP.")

    def clean_before_image(self):
        return self._clean_story_image("before_image")

    def clean_after_image(self):
        return self._clean_story_image("after_image")


# ---------------------------------------------------------------------------
# Inventory forms
# ---------------------------------------------------------------------------

COUNT_REASONS = [
    ("cycle", "Cycle count"),
    ("damage", "Damaged or unusable"),
    ("shrinkage", "Lost or shrinkage"),
    ("correction", "Data correction"),
    ("supplier_return", "Returned to supplier"),
    ("other", "Other"),
]


class SupplierForm(StaffFormMixin, forms.ModelForm):
    class Meta:
        model = Supplier
        fields = (
            "name",
            "contact_name",
            "phone",
            "email",
            "account_number",
            "lead_time_days",
            "notes",
            "is_active",
        )
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "e.g. National Autobody Wholesalers"}),
            "contact_name": forms.TextInput(attrs={"placeholder": "Optional"}),
            "phone": forms.TextInput(attrs={"placeholder": "Optional", "inputmode": "tel"}),
            "email": forms.EmailInput(attrs={"placeholder": "Optional"}),
            "account_number": forms.TextInput(attrs={"placeholder": "Optional"}),
            "notes": forms.Textarea(
                attrs={"rows": 3, "placeholder": "Order days, minimum order, delivery notes."}
            ),
        }
        labels = {
            "name": "Supplier name",
            "contact_name": "Contact person",
            "phone": "Phone",
            "email": "Email",
            "account_number": "Account number",
            "lead_time_days": "Typical lead time (days)",
            "notes": "Notes",
            "is_active": "Use this supplier",
        }
        help_texts = {
            "lead_time_days": "How many days from ordering to the part being on the shelf. Used as a guide, not an automatic order.",
            "is_active": "Archived suppliers stay on old parts but are hidden from the reorder list.",
        }

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            raise ValidationError("Enter a supplier name.")
        return name

    def clean_phone(self):
        return _clean_optional_phone(self.cleaned_data.get("phone"))


class PartForm(StaffFormMixin, forms.ModelForm):
    cost_price = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=0,
        required=False,
        label="Unit cost",
        help_text="What the shop pays. Only masters can see cost.",
    )
    reorder_level = forms.IntegerField(
        min_value=0,
        required=False,
        initial=0,
        label="Reorder when at or below",
    )
    reorder_target = forms.IntegerField(
        min_value=0,
        required=False,
        initial=0,
        label="Restock up to",
    )

    class Meta:
        model = Part
        fields = (
            "sku",
            "name",
            "category",
            "brand",
            "part_number",
            "barcode",
            "bin_location",
            "unit",
            "supplier",
            "cost_price",
            "reorder_level",
            "reorder_target",
            "is_critical",
            "is_active",
            "notes",
        )
        widgets = {
            "sku": forms.TextInput(
                attrs={"placeholder": "e.g. BP-1042 or the supplier number", "autocapitalize": "characters"}
            ),
            "name": forms.TextInput(attrs={"placeholder": "e.g. 3M Panel Bond 08115"}),
            "brand": forms.TextInput(attrs={"placeholder": "Optional"}),
            "part_number": forms.TextInput(attrs={"placeholder": "OEM or manufacturer number"}),
            "barcode": forms.TextInput(
                attrs={"placeholder": "Scan the supplier barcode here", "inputmode": "numeric"}
            ),
            "bin_location": forms.TextInput(
                attrs={"placeholder": "e.g. A-02-3", "autocapitalize": "characters"}
            ),
            "notes": forms.Textarea(
                attrs={"rows": 3, "placeholder": "Fitment notes, alternatives, core charge details."}
            ),
        }
        labels = {
            "sku": "Shop SKU",
            "name": "Part name",
            "category": "Category",
            "brand": "Brand",
            "part_number": "Part number",
            "barcode": "Barcode",
            "bin_location": "Bin location",
            "unit": "Unit",
            "supplier": "Supplier",
            "is_critical": "Critical part — pin it to the top of the reorder list",
            "is_active": "Keep this part active",
            "notes": "Notes",
        }
        help_texts = {
            "sku": "A short unique code. Keep it on the shelf label so it can be scanned or typed.",
            "bin_location": "Use the same zone-aisle-shelf scheme on every shelf label.",
            "reorder_level": "Leave at 0 for one-off or special-order items that are not stocked.",
            "reorder_target": "The quantity to order up to. Must be at least the reorder level.",
            "is_critical": "Use for parts that stop a job when they run out.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["supplier"].queryset = Supplier.objects.filter(is_active=True)
        self.fields["supplier"].empty_label = "No supplier"
        self.fields["cost_price"].initial = self.instance.cost_price if self.instance.pk else Decimal("0.00")
        if self.instance.pk:
            self.fields["reorder_level"].initial = self.instance.reorder_level
            self.fields["reorder_target"].initial = self.instance.reorder_target

    def clean_sku(self):
        sku = (self.cleaned_data.get("sku") or "").strip().upper()
        if not sku:
            raise ValidationError("Enter a shop SKU.")
        existing = Part.objects.exclude(pk=self.instance.pk).filter(sku__iexact=sku)
        if existing.exists():
            raise ValidationError("Another part already uses that SKU.")
        return sku

    def clean_bin_location(self):
        return (self.cleaned_data.get("bin_location") or "").strip().upper()

    def clean(self):
        cleaned = super().clean()
        level = cleaned.get("reorder_level") or 0
        target = cleaned.get("reorder_target") or 0
        cost = cleaned.get("cost_price")
        cleaned["reorder_level"] = level
        cleaned["reorder_target"] = target
        cleaned["cost_price"] = cost if cost is not None else Decimal("0.00")

        if level and not target:
            self.add_error(
                "reorder_target",
                "Set a restock target when a reorder level is set.",
            )
        elif target and target < level:
            self.add_error(
                "reorder_target",
                "The restock target must be at least the reorder level.",
            )
        return cleaned


class ReceiveStockForm(StaffFormMixin, forms.Form):
    quantity = forms.IntegerField(
        min_value=1,
        label="Quantity received",
        widget=forms.NumberInput(attrs={"min": 1, "inputmode": "numeric"}),
    )
    unit_cost = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=0,
        required=False,
        label="Unit cost (optional)",
        help_text="Leave blank to keep the current cost.",
    )
    note = forms.CharField(
        max_length=300,
        required=False,
        label="Note (optional)",
        widget=forms.Textarea(
            attrs={"rows": 2, "placeholder": "Supplier invoice number, delivery note, etc."}
        ),
    )

    def __init__(self, *args, part=None, **kwargs):
        self.part = part
        super().__init__(*args, **kwargs)
        if part and part.cost_price:
            self.fields["unit_cost"].initial = part.cost_price


class UseStockForm(StaffFormMixin, forms.Form):
    quantity = forms.IntegerField(
        min_value=1,
        label="Quantity used",
        widget=forms.NumberInput(attrs={"min": 1, "inputmode": "numeric"}),
    )
    ticket = forms.ModelChoiceField(
        queryset=WorkTicket.objects.none(),
        required=False,
        label="Use on a work ticket (optional)",
        empty_label="Not linked to a ticket",
    )
    note = forms.CharField(
        max_length=300,
        required=False,
        label="Note (optional)",
        widget=forms.Textarea(
            attrs={"rows": 2, "placeholder": "What it was used for, if not linked to a ticket."}
        ),
    )

    def __init__(self, *args, part=None, tickets=None, **kwargs):
        self.part = part
        super().__init__(*args, **kwargs)
        self.fields["ticket"].queryset = tickets if tickets is not None else WorkTicket.objects.none()
        self.fields["ticket"].label_from_instance = lambda ticket: (
            f"{ticket.reference} · {ticket.work_type} · {ticket.vehicle}"
        )
        if part:
            self.fields["quantity"].widget.attrs["max"] = part.quantity_on_hand
            self.fields["quantity"].help_text = (
                f"{part.quantity_on_hand} on the shelf in bin {part.bin_location or 'not set'}."
            )

    def clean_quantity(self):
        quantity = self.cleaned_data.get("quantity")
        if self.part and quantity and quantity > self.part.quantity_on_hand:
            raise ValidationError(
                f"Only {self.part.quantity_on_hand} on the shelf. Receive stock or record a count first."
            )
        return quantity


class CountStockForm(StaffFormMixin, forms.Form):
    counted_quantity = forms.IntegerField(
        min_value=0,
        label="Counted quantity",
        widget=forms.NumberInput(attrs={"min": 0, "inputmode": "numeric"}),
    )
    reason = forms.ChoiceField(choices=COUNT_REASONS, label="Reason")
    note = forms.CharField(
        max_length=300,
        required=False,
        label="Note (optional)",
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "What you found, if useful."}),
    )

    def __init__(self, *args, part=None, **kwargs):
        self.part = part
        super().__init__(*args, **kwargs)
        if part:
            self.fields["counted_quantity"].initial = part.quantity_on_hand


class AdjustStockForm(StaffFormMixin, forms.Form):
    quantity = forms.IntegerField(
        label="Change",
        help_text="Use a negative number to remove stock, for example -2 for damaged parts.",
        widget=forms.NumberInput(attrs={"inputmode": "numeric", "placeholder": "-2 or 3"}),
    )
    reason = forms.ChoiceField(choices=COUNT_REASONS, label="Reason")
    note = forms.CharField(
        max_length=300,
        required=False,
        label="Note (optional)",
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Anything that explains the change."}),
    )

    def clean_quantity(self):
        quantity = self.cleaned_data.get("quantity")
        if quantity == 0:
            raise ValidationError("Enter a change other than zero.")
        return quantity


class InventoryImportForm(StaffFormMixin, forms.Form):
    csv_file = forms.FileField(
        label="CSV file",
        help_text="Use the template columns. Existing SKUs are updated without changing their stock.",
    )
    create_missing_suppliers = forms.BooleanField(
        required=False,
        initial=True,
        label="Create suppliers that are not in the system yet",
    )

    def clean_csv_file(self):
        upload = self.cleaned_data.get("csv_file")
        if not upload:
            return upload
        if upload.size > 1024 * 1024:
            raise ValidationError("Keep the CSV under 1 MB.")
        if not upload.name.lower().endswith(".csv"):
            raise ValidationError("Upload a .csv file.")
        return upload


# ---------------------------------------------------------------------------
# Estimator pricing
# ---------------------------------------------------------------------------


class EstimateServiceForm(StaffFormMixin, forms.ModelForm):
    class Meta:
        model = EstimateService
        fields = (
            "enabled",
            "base_price",
            "spread_percent",
            "unit_label",
            "uses_severity",
            "notes",
        )
        labels = {
            "enabled": "Show this price on the public estimator",
            "base_price": "Base price (CAD)",
            "spread_percent": "Range spread (%)",
            "unit_label": "Pricing basis",
            "uses_severity": "Ask about damage severity",
            "notes": "Internal notes",
        }
        help_texts = {
            "enabled": "Leave this off until the number is one you are happy to publish.",
            "base_price": "The typical price before the vehicle and severity adjustments.",
            "spread_percent": "20 gives a range from 20% below to 20% above the base price.",
            "unit_label": "Shown beside the range, for example ‘per panel’, ‘per axle’ or ‘per job’.",
            "uses_severity": "Body and paint work usually benefits from a minor, moderate or severe choice. Mechanical work usually does not.",
            "notes": "Only the shop sees this. It is a reminder, not public copy.",
        }
        widgets = {
            "base_price": forms.NumberInput(
                attrs={
                    "min": "0",
                    "step": "1",
                    "inputmode": "decimal",
                    "placeholder": "e.g. 450",
                }
            ),
            "spread_percent": forms.NumberInput(
                attrs={"min": "0", "max": "99", "step": "1", "inputmode": "decimal"}
            ),
            "unit_label": forms.TextInput(attrs={"placeholder": "per job"}),
            "notes": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "How this number was set, when to review it, and anything the shop should remember.",
                }
            ),
        }

    def clean(self):
        data = super().clean()
        if data.get("enabled") and not data.get("base_price"):
            self.add_error(
                "base_price",
                "Enter a base price before turning this estimate on.",
            )
        return data


class EstimateAddOnForm(StaffFormMixin, forms.ModelForm):
    class Meta:
        model = EstimateAddOn
        fields = ("label", "amount", "enabled", "display_order")
        labels = {
            "label": "Add-on name",
            "amount": "Amount (CAD)",
            "enabled": "Offer this add-on",
            "display_order": "Order",
        }
        help_texts = {
            "label": "For example ‘Blend adjacent panel’ or ‘Rust treatment’.",
            "amount": "A flat amount added to both ends of the range.",
            "display_order": "Lower numbers appear first.",
        }
        widgets = {
            "label": forms.TextInput(attrs={"placeholder": "e.g. Blend adjacent panel"}),
            "amount": forms.NumberInput(
                attrs={"min": "0", "step": "1", "inputmode": "decimal", "placeholder": "e.g. 120"}
            ),
            "display_order": forms.NumberInput(attrs={"min": "0", "step": "1"}),
        }


class EstimateSettingsForm(StaffFormMixin, forms.ModelForm):
    class Meta:
        model = EstimateSettings
        fields = (
            "site_enabled",
            "rounding_step",
            "car_multiplier",
            "suv_multiplier",
            "luxury_multiplier",
            "severity_minor",
            "severity_moderate",
            "severity_severe",
            "prices_updated_on",
            "disclaimer",
        )
        labels = {
            "site_enabled": "Turn the public estimator on",
            "rounding_step": "Round prices to",
            "car_multiplier": "Car or small SUV",
            "suv_multiplier": "SUV, van or pickup",
            "luxury_multiplier": "Luxury or premium",
            "severity_minor": "Minor damage",
            "severity_moderate": "Moderate damage",
            "severity_severe": "Severe damage",
            "prices_updated_on": "Prices last reviewed",
            "disclaimer": "Disclaimer shown with every estimate",
        }
        help_texts = {
            "site_enabled": "Off means the page stays up but shows ‘call for pricing’ instead of a range.",
            "rounding_step": "The low end rounds down and the high end rounds up to this step.",
            "car_multiplier": "1.00 leaves the base price unchanged.",
            "suv_multiplier": "A multiplier of 1.15 adds 15% before rounding.",
            "luxury_multiplier": "Use this for premium makes and finishes that take longer to match.",
            "severity_minor": "Only used by services that ask about damage severity.",
            "severity_moderate": "Only used by services that ask about damage severity.",
            "severity_severe": "Only used by services that ask about damage severity.",
            "prices_updated_on": "Shown to visitors beside the range. Leave blank to hide it.",
            "disclaimer": "Keep the ‘not a quote’ wording. It is the honest boundary of this tool.",
        }
        widgets = {
            "prices_updated_on": forms.DateInput(attrs={"type": "date"}),
            "disclaimer": forms.Textarea(attrs={"rows": 4}),
        }

    MULTIPLIER_FIELDS = (
        "car_multiplier",
        "suv_multiplier",
        "luxury_multiplier",
        "severity_minor",
        "severity_moderate",
        "severity_severe",
    )

    def clean(self):
        data = super().clean()
        for field in self.MULTIPLIER_FIELDS:
            value = data.get(field)
            if value is not None and value <= 0:
                self.add_error(field, "The multiplier must be greater than zero.")
        return data
