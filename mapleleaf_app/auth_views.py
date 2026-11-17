"""The public sign-in page shared by staff and customers.

Everyone uses one form. The account itself decides where the person lands:
the shop dashboard, the employee work list, or the customer account. Visitors
are never asked to pick a role up front.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from django.contrib import messages
from django.contrib.auth import login
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache

from .customer_access import get_customer_profile
from .login_throttle import (
    clear_login_failures,
    login_blocked,
    record_login_failure,
)
from .roles import account_home_name, get_staff_role
from .staff_forms import StaffAuthenticationForm

NO_ACCESS_MESSAGE = (
    "This account does not have access to a sign-in area. "
    "Please contact the shop if you need help."
)


def _display_name(user):
    return (user.get_full_name() or user.get_username() or "there").strip()


def _allowed_next(request, user, next_url):
    """Only continue into an area the signed-in account can actually open."""

    if not next_url:
        return None
    if not url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return None

    path = urlsplit(next_url).path
    if get_staff_role(user) and path.startswith("/staff/"):
        return next_url
    if get_customer_profile(user) and path.startswith("/account/"):
        return next_url
    return None


@never_cache
def sign_in(request):
    destination = account_home_name(request.user)
    if destination:
        return redirect(destination)

    next_url = request.POST.get("next") or request.GET.get("next") or ""
    form = StaffAuthenticationForm(request=request, data=request.POST or None)

    if request.method == "POST":
        if login_blocked(request):
            form.add_error(
                None,
                "Too many sign-in attempts. Wait 15 minutes, then try again.",
            )
        elif form.is_valid():
            user = form.get_user()
            destination = account_home_name(user)
            if not destination:
                form.add_error(None, NO_ACCESS_MESSAGE)
                record_login_failure(request)
            else:
                clear_login_failures(request)
                login(request, user)
                messages.success(request, f"Signed in as {_display_name(user)}.")
                return redirect(_allowed_next(request, user, next_url) or destination)
        else:
            record_login_failure(request)

    return render(
        request,
        "auth/login.html",
        {
            "form": form,
            "next": next_url,
            "page_title": "Sign in",
        },
    )
