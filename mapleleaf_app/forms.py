"""Validated forms for the site's lead, booking and photo workflows."""

import re
from datetime import date, timedelta

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.images import get_image_dimensions

from .content import CALLBACK_WINDOWS, DROP_OFF_WINDOWS, SERVICES
from .estimating import CLAIM_CHOICES, SEVERITY_CHOICES, VEHICLE_CLASSES, money
from .models import EstimateAddOn

PHONE_ERROR = "That phone number looks too short. Please check it."
PHOTO_LIMIT = getattr(settings, "PHOTO_UPLOAD_MAX_FILES", 4)
PHOTO_MAX_BYTES = getattr(settings, "PHOTO_UPLOAD_MAX_BYTES", 6 * 1024 * 1024)
PHOTO_TYPES = {"image/jpeg", "image/png", "image/webp"}


def _phone_digits(value):
    return re.sub(r"\D", "", value or "")


def validate_phone(value):
    if len(_phone_digits(value)) < 7:
        raise ValidationError(PHONE_ERROR)
    return value


def _future_booking_dates(days=28):
    """Return weekday dates, excluding Sundays, for the preferred-window picker."""
    today = date.today()
    options = []
    cursor = today
    while len(options) < days:
        if cursor.weekday() != 6:  # Sunday
            options.append((cursor.isoformat(), f"{cursor:%a %b} {cursor.day}"))
        cursor += timedelta(days=1)
    return options


def _service_choices():
    return [(service["title"], service["title"]) for service in SERVICES] + [("Not sure yet", "Not sure yet")]


def _apply_field_styles(form):
    for name, field in form.fields.items():
        widget = field.widget
        if isinstance(widget, (forms.HiddenInput, forms.CheckboxInput, forms.FileInput, forms.RadioSelect)):
            continue
        existing = widget.attrs.get("class", "")
        widget.attrs["class"] = (existing + " field").strip()
        if field.help_text and "aria-describedby" not in widget.attrs:
            widget.attrs["aria-describedby"] = f"id_{name}_help"


class StyledFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_field_styles(self)


class BookingForm(StyledFormMixin, forms.Form):
    full_name = forms.CharField(max_length=100, label="Your name")
    phone_number = forms.CharField(max_length=40, label="Phone")
    email = forms.EmailField(max_length=160, required=False, label="Email (optional)")
    vehicle = forms.CharField(max_length=160, label="Vehicle")
    service = forms.ChoiceField(choices=(), label="What do you need?")
    preferred_date = forms.ChoiceField(choices=(), label="Preferred drop-off date")
    preferred_window = forms.ChoiceField(choices=DROP_OFF_WINDOWS, label="Preferred window")
    visit_type = forms.ChoiceField(
        choices=[("drop_off", "Drop off the vehicle"), ("wait", "Wait at the shop")],
        label="Drop-off or wait?",
        initial="drop_off",
        widget=forms.RadioSelect,
    )
    notes = forms.CharField(
        max_length=1200,
        required=False,
        label="Vehicle details & notes",
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "Year, make, model, claim number, or anything helpful."}),
    )
    privacy_consent = forms.BooleanField(label="I agree to be contacted about this request.")
    website = forms.CharField(required=False, widget=forms.HiddenInput())  # honeypot

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["service"].choices = _service_choices()
        self.fields["preferred_date"].choices = _future_booking_dates()
        self.order_fields(
            [
                "full_name",
                "phone_number",
                "email",
                "vehicle",
                "service",
                "preferred_date",
                "preferred_window",
                "visit_type",
                "notes",
                "privacy_consent",
                "website",
            ]
        )

    def clean_phone_number(self):
        return validate_phone(self.cleaned_data["phone_number"])

    def clean_preferred_date(self):
        value = self.cleaned_data["preferred_date"]
        try:
            chosen = date.fromisoformat(value)
        except ValueError:
            raise ValidationError("Please choose a valid date.")
        if chosen < date.today():
            raise ValidationError("Please choose today or a future date.")
        if chosen.weekday() == 6:
            raise ValidationError("The shop is closed on Sundays. Please choose another day.")
        return value

    def clean_website(self):
        value = self.cleaned_data.get("website")
        if value:
            raise ValidationError("Spam detected.")
        return value


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleImageField(forms.FileField):
    widget = MultipleFileInput

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput(attrs={"accept": "image/jpeg,image/png,image/webp", "multiple": True}))
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_clean = super().clean
        if isinstance(data, (list, tuple)):
            return [single_clean(item, initial) for item in data if item]
        return [single_clean(data, initial)] if data else []


def validate_photo_file(upload):
    if upload.size > PHOTO_MAX_BYTES:
        raise ValidationError(f"Each photo must be smaller than {PHOTO_MAX_BYTES // (1024 * 1024)} MB.")
    content_type = getattr(upload, "content_type", "")
    if content_type and content_type.lower() not in PHOTO_TYPES:
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
    return upload


class PhotoRequestForm(StyledFormMixin, forms.Form):
    DAMAGE_TYPES = [
        ("", "Choose the closest match"),
        ("windshield", "Windshield chip or crack"),
        ("collision", "Collision or body damage"),
        ("dent", "Dent, scratch or paint damage"),
        ("mechanical", "Mechanical or warning-light issue"),
        ("other", "Something else"),
    ]

    full_name = forms.CharField(max_length=100, label="Your name")
    phone_number = forms.CharField(max_length=40, label="Phone")
    email = forms.EmailField(max_length=160, required=False, label="Email (optional)")
    vehicle = forms.CharField(max_length=160, label="Vehicle")
    damage_type = forms.ChoiceField(choices=DAMAGE_TYPES, label="What are we looking at?")
    description = forms.CharField(
        max_length=1200,
        required=False,
        label="What happened?",
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "Tell us what you noticed and when it started."}),
    )
    preferred_time = forms.ChoiceField(choices=CALLBACK_WINDOWS, label="Best time to call", initial="Anytime today")
    photos = MultipleImageField(
        label="Damage photos",
        help_text=f"Up to {PHOTO_LIMIT} photos. JPEG, PNG or WebP, max {PHOTO_MAX_BYTES // (1024 * 1024)} MB each. Photos are compressed before storage.",
    )
    privacy_consent = forms.BooleanField(
        label="I agree to Maple Leaf storing these photos to assess my request.",
    )
    website = forms.CharField(required=False, widget=forms.HiddenInput())  # honeypot

    def clean_phone_number(self):
        return validate_phone(self.cleaned_data["phone_number"])

    def clean_photos(self):
        photos = self.cleaned_data.get("photos") or []
        if not photos:
            raise ValidationError("Add at least one photo so we can see the damage.")
        if len(photos) > PHOTO_LIMIT:
            raise ValidationError(f"Please upload no more than {PHOTO_LIMIT} photos.")
        return [validate_photo_file(photo) for photo in photos]

    def clean_website(self):
        value = self.cleaned_data.get("website")
        if value:
            raise ValidationError("Spam detected.")
        return value


class ClaimIntakeForm(StyledFormMixin, forms.Form):
    full_name = forms.CharField(max_length=100, label="Your name")
    phone_number = forms.CharField(max_length=40, label="Phone")
    email = forms.EmailField(max_length=160, required=False, label="Email (optional)")
    claim_number = forms.CharField(max_length=60, required=False, label="MPI claim number")
    has_claim = forms.ChoiceField(
        required=False,
        choices=[("yes", "Yes"), ("no", "No"), ("unsure", "Not sure")],
        label="Do you have an MPI claim number?",
        widget=forms.HiddenInput(),
    )
    anyone_injured = forms.ChoiceField(
        required=False,
        choices=[("yes", "Yes"), ("no", "No")],
        label="Was anyone injured?",
        widget=forms.HiddenInput(),
    )
    vehicle_drivable = forms.ChoiceField(
        required=False,
        choices=[("yes", "Yes"), ("no", "No")],
        label="Is the vehicle drivable?",
        widget=forms.HiddenInput(),
    )
    registered_owner = forms.ChoiceField(
        required=False,
        choices=[("yes", "Yes"), ("no", "No")],
        label="Are you the registered owner?",
        widget=forms.HiddenInput(),
    )
    damage_description = forms.CharField(
        max_length=1200,
        required=False,
        label="What happened?",
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "A short description of the damage helps us prepare."}),
    )
    preferred_time = forms.ChoiceField(choices=CALLBACK_WINDOWS, label="Best time to call", initial="Anytime today")
    result_summary = forms.CharField(required=False, widget=forms.HiddenInput())
    website = forms.CharField(required=False, widget=forms.HiddenInput())  # honeypot

    def clean_phone_number(self):
        return validate_phone(self.cleaned_data["phone_number"])

    def clean_website(self):
        value = self.cleaned_data.get("website")
        if value:
            raise ValidationError("Spam detected.")
        return value


class EstimateDetailsForm(StyledFormMixin, forms.Form):
    """Step two of the public repair estimator.

    The add-on choices are scoped to the chosen service in ``__init__`` so a
    visitor can never attach a brake add-on to a windshield estimate. Severity
    is only asked for services the master marked as body or paint work.
    """

    vehicle_class = forms.ChoiceField(
        choices=VEHICLE_CLASSES,
        initial="car",
        label="Vehicle type",
        widget=forms.RadioSelect,
    )
    severity = forms.ChoiceField(
        choices=SEVERITY_CHOICES,
        initial="moderate",
        required=False,
        label="How bad is the damage?",
        widget=forms.RadioSelect,
    )
    claim_type = forms.ChoiceField(
        choices=CLAIM_CHOICES,
        initial="private",
        label="How is this being paid for?",
        widget=forms.RadioSelect,
    )
    addons = forms.ModelMultipleChoiceField(
        queryset=EstimateAddOn.objects.none(),
        required=False,
        label="Extra work to include",
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, service=None, **kwargs):
        self.service = service
        super().__init__(*args, **kwargs)
        if service is not None:
            self.fields["addons"].queryset = service.addons.filter(enabled=True)
            self.fields["addons"].label_from_instance = (
                lambda addon: f"{addon.label} (+{money(addon.amount)})"
            )
            if not service.uses_severity:
                self.fields.pop("severity", None)
        else:
            self.fields.pop("severity", None)
