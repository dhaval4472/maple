"""Customer account helpers.

Customer accounts are created by the shop, never through a public sign-up.
Requests are linked by the email address or phone number on the account. The
matching happens here so the public form views and the staff account tools use
exactly the same rules.
"""

from __future__ import annotations

import re

from .models import (
    BookingRequest,
    CallbackRequest,
    ClaimIntake,
    CustomerProfile,
    PhotoRequest,
)

REQUEST_MODELS = (CallbackRequest, ClaimIntake, BookingRequest, PhotoRequest)


def normalize_email(value):
    return (value or "").strip().lower()


def normalize_phone(value):
    digits = re.sub(r"\D", "", value or "")
    # A short string such as an extension is not a usable identity match.
    return digits if len(digits) >= 7 else ""


def get_customer_profile(user):
    """Return the customer profile for an active signed-in user, if any."""

    if not user or not user.is_authenticated or not user.is_active:
        return None
    return getattr(user, "customer_profile", None)


def is_customer(user):
    return get_customer_profile(user) is not None


def identity_matches(profile, email="", phone=""):
    if not profile:
        return False
    account_email = normalize_email(profile.user.email)
    account_phone = normalize_phone(profile.phone)
    email = normalize_email(email)
    phone = normalize_phone(phone)
    return bool(
        (email and account_email and email == account_email)
        or (phone and account_phone and phone == account_phone)
    )


def customer_for_submission(user, email="", phone=""):
    """Return the signed-in customer when a public form uses their identity.

    A customer can submit a request for someone else. In that case the request
    stays unlinked until the shop chooses to connect it.
    """

    profile = get_customer_profile(user)
    if identity_matches(profile, email, phone):
        return user
    return None


def link_customer_requests(profile):
    """Attach unlinked requests that match the customer's email or phone.

    Existing links are never overwritten, so a later edit to a customer's
    contact details cannot move another customer's request. Returns the number
    of requests newly linked.
    """

    if not profile:
        return 0

    email = normalize_email(profile.user.email)
    phone = normalize_phone(profile.phone)
    if not email and not phone:
        return 0

    linked = 0
    for model in REQUEST_MODELS:
        for obj in model.objects.filter(customer__isnull=True).iterator():
            obj_email = normalize_email(getattr(obj, "email", ""))
            obj_phone = normalize_phone(obj.phone_number)
            if (email and obj_email and email == obj_email) or (
                phone and obj_phone and phone == obj_phone
            ):
                obj.customer_id = profile.user_id
                obj.save(update_fields=["customer", "updated_at"])
                linked += 1
    return linked
