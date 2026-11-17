"""Customer sign-in and account pages.

Customers never sign themselves up. The shop creates the account and shares the
username and temporary password. A customer can only see requests linked to
that account.
"""

from __future__ import annotations

from functools import wraps
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.formats import date_format
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from .customer_access import get_customer_profile
from .customer_forms import CustomerAuthenticationForm
from .login_throttle import (
    clear_login_failures as _clear_failures,
    login_blocked as _login_blocked,
    record_login_failure as _record_failure,
)
from .models import BookingRequest, CallbackRequest, ClaimIntake, PhotoRequest
from .staff_forms import StaffPasswordChangeForm


def _login_redirect(request):
    login_url = reverse("customer_login")
    return redirect(f"{login_url}?{urlencode({'next': request.get_full_path()})}")


def customer_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return _login_redirect(request)
        profile = get_customer_profile(request.user)
        if not profile:
            messages.error(request, "This account does not have customer access.")
            return redirect("customer_login")
        request.customer_profile = profile
        return view(request, *args, **kwargs)

    return never_cache(wrapped)


def _display_name(user):
    return user.get_full_name() or user.get_username()


@never_cache
def customer_login(request):
    if request.user.is_authenticated and get_customer_profile(request.user):
        return redirect("customer_dashboard")

    next_url = request.POST.get("next") or request.GET.get("next") or ""
    form = CustomerAuthenticationForm(request=request, data=request.POST or None)

    if request.method == "POST":
        if _login_blocked(request):
            form.add_error(
                None,
                "Too many sign-in attempts. Wait 15 minutes, then try again.",
            )
        elif form.is_valid():
            user = form.get_user()
            if not get_customer_profile(user):
                form.add_error(
                    None,
                    "This account does not have customer access. Ask the shop to set up an account for you.",
                )
                _record_failure(request)
            else:
                _clear_failures(request)
                login(request, user)
                messages.success(request, f"Signed in as {_display_name(user)}.")
                if next_url and url_has_allowed_host_and_scheme(
                    next_url,
                    allowed_hosts={request.get_host()},
                    require_https=request.is_secure(),
                ):
                    return redirect(next_url)
                return redirect("customer_dashboard")
        else:
            _record_failure(request)

    return render(
        request,
        "customer/login.html",
        {"form": form, "next": next_url, "page_title": "Customer sign in"},
    )


@require_POST
def customer_logout(request):
    logout(request)
    messages.success(request, "You have been signed out.")
    return redirect("customer_login")


STATUS_TONES = {
    "new": "new",
    "contacted": "progress",
    "booked": "good",
    "confirmed": "good",
    "reviewed": "progress",
    "quoted": "good",
    "completed": "muted",
    "closed": "muted",
    "declined": "bad",
}

STATUS_LABELS = {
    "new": "Received",
    "contacted": "Shop followed up",
    "booked": "Booked",
    "confirmed": "Confirmed by shop",
    "reviewed": "Reviewed by shop",
    "quoted": "Estimate ready",
    "completed": "Completed",
    "closed": "Closed",
    "declined": "Could not book",
}


def _status_tone(status):
    return STATUS_TONES.get(status, "progress")


def _request_rows(user):
    rows = []

    for booking in BookingRequest.objects.filter(customer=user):
        rows.append(
            {
                "kind": "Booking request",
                "icon": "calendar_month",
                "reference": booking.reference,
                "status": STATUS_LABELS.get(booking.status, booking.get_status_display()),
                "tone": _status_tone(booking.status),
                "created": booking.created_at,
                "headline": booking.vehicle,
                "detail": f"{booking.service} · {date_format(booking.preferred_date, 'M j, Y')} · {booking.preferred_window}",
                "note": booking.notes,
            }
        )

    for callback in CallbackRequest.objects.filter(customer=user):
        rows.append(
            {
                "kind": "Callback request",
                "icon": "phone_in_talk",
                "reference": callback.reference,
                "status": STATUS_LABELS.get(callback.status, callback.get_status_display()),
                "tone": _status_tone(callback.status),
                "created": callback.created_at,
                "headline": callback.service_needed,
                "detail": f"Best time: {callback.preferred_time}",
                "note": callback.vehicle_description,
            }
        )

    for claim in ClaimIntake.objects.filter(customer=user):
        rows.append(
            {
                "kind": "MPI claim question",
                "icon": "assignment",
                "reference": claim.reference,
                "status": STATUS_LABELS.get(claim.status, claim.get_status_display()),
                "tone": _status_tone(claim.status),
                "created": claim.created_at,
                "headline": f"Claim {claim.claim_number}" if claim.claim_number else "MPI claim question",
                "detail": claim.damage_description or "Claim navigator request",
                "note": claim.preferred_time,
            }
        )

    for photo in PhotoRequest.objects.filter(customer=user):
        rows.append(
            {
                "kind": "Photo request",
                "icon": "photo_camera",
                "reference": photo.reference,
                "status": STATUS_LABELS.get(photo.status, photo.get_status_display()),
                "tone": _status_tone(photo.status),
                "created": photo.created_at,
                "headline": photo.vehicle,
                "detail": f"{photo.get_damage_type_display()} · {photo.photos.count()} photo{'s' if photo.photos.count() != 1 else ''}",
                "note": photo.description,
            }
        )

    rows.sort(key=lambda row: row["created"], reverse=True)
    return rows


@customer_required
def customer_dashboard(request):
    rows = _request_rows(request.user)
    active = [row for row in rows if row["tone"] in {"new", "progress", "good"}]
    return render(
        request,
        "customer/dashboard.html",
        {
            "page_title": "My requests",
            "nav": "requests",
            "customer_profile": request.customer_profile,
            "rows": rows,
            "active_count": len(active),
            "total_count": len(rows),
        },
    )


@customer_required
def customer_password_change(request):
    form = StaffPasswordChangeForm(request.user, request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            form.save()
            update_session_auth_hash(request, form.user)
            messages.success(request, "Your password was changed.")
            return redirect("customer_dashboard")
        messages.error(request, "Please fix the highlighted fields.")

    return render(
        request,
        "customer/password.html",
        {
            "page_title": "Change password",
            "nav": "password",
            "customer_profile": request.customer_profile,
            "form": form,
        },
    )
