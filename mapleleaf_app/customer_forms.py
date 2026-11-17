"""Forms for shop-created customer accounts and customer sign-in."""

from __future__ import annotations

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.core.exceptions import ValidationError

from .customer_access import normalize_email, normalize_phone
from .forms import StyledFormMixin, _apply_field_styles, validate_phone
from .models import CustomerProfile


class CustomerAuthenticationForm(AuthenticationForm):
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


def _clean_phone(value):
    value = (value or "").strip()
    if value:
        validate_phone(value)
    return value


def _phone_is_used(value, exclude_user=None):
    phone = normalize_phone(value)
    if not phone:
        return False
    profiles = CustomerProfile.objects.select_related("user")
    if exclude_user is not None:
        profiles = profiles.exclude(user=exclude_user)
    return any(normalize_phone(profile.phone) == phone for profile in profiles)


class CustomerCreateForm(StyledFormMixin, UserCreationForm):
    first_name = forms.CharField(max_length=150, label="First name")
    last_name = forms.CharField(max_length=150, label="Last name")
    email = forms.EmailField(max_length=254, required=False, label="Email address")
    phone = forms.CharField(max_length=40, required=False, label="Phone number")

    class Meta:
        model = get_user_model()
        fields = ("username", "first_name", "last_name", "email")
        labels = {"username": "Sign-in username"}
        help_texts = {
            "username": "The customer uses this with the password you share with them.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_field_styles(self)
        self.fields["username"].widget.attrs["placeholder"] = "e.g. jsmith"
        self.fields["first_name"].widget.attrs["placeholder"] = "Jamie"
        self.fields["last_name"].widget.attrs["placeholder"] = "Smith"
        self.fields["email"].widget.attrs["placeholder"] = "Optional if you add a phone"
        self.fields["phone"].widget.attrs["placeholder"] = "Optional if you add an email"

    def clean_email(self):
        email = normalize_email(self.cleaned_data.get("email"))
        if email and get_user_model().objects.filter(email__iexact=email).exists():
            raise ValidationError("An account with this email address already exists.")
        return email

    def clean_phone(self):
        phone = _clean_phone(self.cleaned_data.get("phone"))
        if _phone_is_used(phone):
            raise ValidationError("A customer account already uses this phone number.")
        return phone

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("email") and not cleaned.get("phone"):
            raise ValidationError(
                "Add an email address, a phone number, or both so requests can be linked."
            )
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_staff = False
        user.is_superuser = False
        user.email = self.cleaned_data.get("email", "")
        if commit:
            user.save()
            CustomerProfile.objects.create(
                user=user,
                phone=self.cleaned_data.get("phone", ""),
            )
        return user


class CustomerProfileForm(StyledFormMixin, forms.ModelForm):
    phone = forms.CharField(
        max_length=40,
        required=False,
        label="Phone number",
        help_text="Used to match requests that were submitted with this number.",
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
        _apply_field_styles(self)
        profile = getattr(self.instance, "customer_profile", None)
        if profile:
            self.fields["phone"].initial = profile.phone

    def clean_email(self):
        email = normalize_email(self.cleaned_data.get("email"))
        if (
            email
            and get_user_model()
            .objects.filter(email__iexact=email)
            .exclude(pk=self.instance.pk)
            .exists()
        ):
            raise ValidationError("An account with this email address already exists.")
        return email

    def clean_phone(self):
        phone = _clean_phone(self.cleaned_data.get("phone"))
        if _phone_is_used(phone, exclude_user=self.instance):
            raise ValidationError("A customer account already uses this phone number.")
        return phone

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("email") and not cleaned.get("phone"):
            raise ValidationError(
                "Keep at least one email address or phone number so requests can be matched."
            )
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            profile, _created = CustomerProfile.objects.get_or_create(user=user)
            profile.phone = self.cleaned_data.get("phone", "")
            profile.save(update_fields=["phone", "updated_at"])
        return user
