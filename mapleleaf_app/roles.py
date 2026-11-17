"""Workspace role helpers shared by views, templates and navigation."""

from __future__ import annotations

from django.contrib.auth import get_user_model

from .customer_access import get_customer_profile
from .models import StaffProfile


def get_staff_role(user):
    """Return ``master``, ``employee`` or ``None`` for a user.

    Existing Django staff accounts are treated as masters so the original
    owner account keeps working. Employee accounts only need a profile and
    never need Django staff access.
    """

    if not user or not user.is_authenticated or not user.is_active:
        return None

    profile = getattr(user, "staff_profile", None)
    if profile and profile.role in dict(StaffProfile.ROLE_CHOICES):
        return profile.role

    if user.is_superuser or user.is_staff:
        StaffProfile.objects.get_or_create(
            user=user,
            defaults={"role": StaffProfile.ROLE_MASTER},
        )
        return StaffProfile.ROLE_MASTER

    return None


def is_master(user):
    return get_staff_role(user) == StaffProfile.ROLE_MASTER


def is_employee(user):
    return get_staff_role(user) == StaffProfile.ROLE_EMPLOYEE


def employee_users():
    """Active accounts that can be assigned work."""

    return get_user_model().objects.filter(
        staff_profile__role=StaffProfile.ROLE_EMPLOYEE,
        is_active=True,
    )


def workspace_home_name(user):
    """URL name for the page a signed-in workspace user should land on."""

    if is_master(user):
        return "staff_dashboard"
    if is_employee(user):
        return "staff_my_work"
    return "staff_login"


def account_home_name(user):
    """URL name of the area tied to an account, or ``None`` for no access."""

    role = get_staff_role(user)
    if role == StaffProfile.ROLE_MASTER:
        return "staff_dashboard"
    if role == StaffProfile.ROLE_EMPLOYEE:
        return "staff_my_work"
    if get_customer_profile(user):
        return "customer_dashboard"
    return None


def account_home_label(user):
    """Short navigation label for the account area, or an empty string."""

    role = get_staff_role(user)
    if role == StaffProfile.ROLE_MASTER:
        return "Dashboard"
    if role == StaffProfile.ROLE_EMPLOYEE:
        return "My work"
    if get_customer_profile(user):
        return "My account"
    return ""
