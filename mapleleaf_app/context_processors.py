"""Template context for the role-aware staff navigation badges."""

from __future__ import annotations

from django.db.models import F
from django.utils import timezone

from .models import (
    BookingRequest,
    CallbackRequest,
    ClaimIntake,
    Part,
    PhotoRequest,
    StaffProfile,
    WorkTicket,
)
from .roles import account_home_label, account_home_name, get_staff_role


def account_nav(request):
    """Expose the signed-in account destination to the public chrome."""

    user = getattr(request, "user", None)
    home = account_home_name(user)
    if not home:
        return {}
    return {
        "account_home_name": home,
        "account_label": account_home_label(user),
    }


def staff_nav_counts(request):
    user = getattr(request, "user", None)
    role = get_staff_role(user)
    if not role:
        return {}

    if role == StaffProfile.ROLE_MASTER:
        return {
            "staff_new_callbacks": CallbackRequest.objects.filter(status="new").count(),
            "staff_new_bookings": BookingRequest.objects.filter(status="new").count(),
            "staff_new_claims": ClaimIntake.objects.filter(status="new").count(),
            "staff_new_photos": PhotoRequest.objects.filter(status="new").count(),
            "staff_open_tickets": WorkTicket.objects.filter(
                status__in=WorkTicket.OPEN_STATUSES
            ).count(),
            "staff_overdue_tickets": WorkTicket.objects.filter(
                status__in=WorkTicket.OPEN_STATUSES,
                due_date__lt=timezone.localdate(),
            ).count(),
            "staff_low_stock": Part.objects.filter(
                is_active=True,
                reorder_level__gt=0,
                quantity_on_hand__lte=F("reorder_level"),
            ).count(),
        }

    mine = WorkTicket.objects.filter(assignee=user)
    return {
        "staff_my_open_tickets": mine.filter(
            status__in=WorkTicket.OPEN_STATUSES
        ).count(),
        "staff_my_in_progress_tickets": mine.filter(
            status=WorkTicket.STATUS_IN_PROGRESS
        ).count(),
    }
