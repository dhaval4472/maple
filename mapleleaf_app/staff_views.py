"""Staff-facing dashboard and management views.

Everything in this module is restricted to active staff accounts. The public
site never imports these views, so shop-side tools cannot be reached by a
visitor who is not signed in.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, F, Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from .inventory import (
    low_stock_count,
    low_stock_parts,
    record_movement,
    reorder_groups,
    ticket_part_rows,
    ticket_parts_total,
    usage_since,
)
from .login_throttle import (
    clear_login_failures as _clear_login_failures,
    login_blocked as _login_blocked,
    record_login_failure as _record_login_failure,
)
from .customer_access import link_customer_requests
from .customer_forms import CustomerCreateForm, CustomerProfileForm
from .models import (
    AnalyticsEvent,
    BookingRequest,
    CallbackRequest,
    ClaimIntake,
    CustomerProfile,
    EstimateAddOn,
    EstimateService,
    EstimateSettings,
    Part,
    PhotoRequest,
    PhotoRequestImage,
    RepairStory,
    Review,
    StaffProfile,
    StockMovement,
    Supplier,
    WorkTicket,
)
from .roles import (
    employee_users,
    get_staff_role,
    is_employee,
    is_master,
    workspace_home_name,
)
from .staff_forms import (
    AdjustStockForm,
    BookingUpdateForm,
    CallbackUpdateForm,
    ClaimUpdateForm,
    COUNT_REASONS,
    CountStockForm,
    EmployeeCreateForm,
    EstimateAddOnForm,
    EstimateServiceForm,
    EstimateSettingsForm,
    EmployeeSetPasswordForm,
    InventoryImportForm,
    PartForm,
    PhotoUpdateForm,
    ReceiveStockForm,
    RepairStoryForm,
    ReviewForm,
    StaffAuthenticationForm,
    StaffPasswordChangeForm,
    StaffProfileForm,
    SupplierForm,
    UseStockForm,
    WorkTicketForm,
    WorkTicketNoteForm,
)

LEAD_CONFIG = {
    "callback": {
        "model": CallbackRequest,
        "label": "Callback request",
        "plural": "Callbacks",
        "nav": "callbacks",
        "icon": "phone_in_talk",
        "list_url": "staff_callbacks",
        "detail_url": "staff_callback_detail",
        "form": CallbackUpdateForm,
        "description": "People who asked the shop to call them back.",
        "search_fields": ("reference", "full_name", "phone_number", "service_needed", "vehicle_description"),
        "search_placeholder": "Search name, phone, reference or service",
    },
    "booking": {
        "model": BookingRequest,
        "label": "Booking request",
        "plural": "Bookings",
        "nav": "bookings",
        "icon": "calendar_month",
        "list_url": "staff_bookings",
        "detail_url": "staff_booking_detail",
        "form": BookingUpdateForm,
        "description": "Preferred drop-off windows waiting for the shop to confirm capacity.",
        "search_fields": ("reference", "full_name", "phone_number", "email", "vehicle", "service"),
        "search_placeholder": "Search name, phone, vehicle or reference",
    },
    "claim": {
        "model": ClaimIntake,
        "label": "MPI claim intake",
        "plural": "MPI claims",
        "nav": "claims",
        "icon": "assignment",
        "list_url": "staff_claims",
        "detail_url": "staff_claim_detail",
        "form": ClaimUpdateForm,
        "description": "Claim navigator answers and callback details from MPI questions.",
        "search_fields": ("reference", "full_name", "phone_number", "email", "claim_number", "damage_description"),
        "search_placeholder": "Search name, phone, claim number or reference",
    },
    "photo": {
        "model": PhotoRequest,
        "label": "Photo request",
        "plural": "Photo requests",
        "nav": "photos",
        "icon": "photo_camera",
        "list_url": "staff_photos",
        "detail_url": "staff_photo_detail",
        "form": PhotoUpdateForm,
        "description": "Damage photos sent for a first look before an in-person estimate.",
        "search_fields": ("reference", "full_name", "phone_number", "email", "vehicle", "damage_type", "description"),
        "search_placeholder": "Search name, phone, vehicle or reference",
    },
}

EVENT_LABELS = {
    "page_view": "Page views",
    "phone_click": "Phone clicks",
    "callback_open": "Callback forms opened",
    "callback_submit": "Callback requests sent",
    "claim_navigator_start": "Claim navigator started",
    "claim_navigator_complete": "Claim navigator completed",
    "claim_navigator_submit": "Claim navigator sent",
    "chip_checker_result": "Chip checker results",
    "chip_checker_submit": "Chip checker sent",
    "repair_replace_result": "Repair-or-replace results",
    "repair_replace_submit": "Repair-or-replace sent",
    "booking_start": "Booking forms started",
    "booking_submit": "Booking requests sent",
    "photo_request_start": "Photo forms started",
    "photo_request_submit": "Photo requests sent",
    "service_view": "Service page views",
    "tool_view": "Tool page views",
    "gallery_view": "Gallery opens",
    "review_filter": "Review filters used",
}

NAV_ITEMS = [
    ("dashboard", "Dashboard", "space_dashboard", "staff_dashboard", None),
    ("callbacks", "Callbacks", "phone_in_talk", "staff_callbacks", "callback"),
    ("bookings", "Bookings", "calendar_month", "staff_bookings", "booking"),
    ("claims", "MPI claims", "assignment", "staff_claims", "claim"),
    ("photos", "Photo requests", "photo_camera", "staff_photos", "photo"),
]

CONTENT_ITEMS = [
    ("estimator", "Estimator", "request_quote", "staff_estimator", None),
    ("reviews", "Reviews", "reviews", "staff_reviews", None),
    ("stories", "Repair stories", "auto_stories", "staff_stories", None),
    ("analytics", "Website activity", "monitoring", "staff_analytics", None),
    ("account", "My account", "manage_accounts", "staff_account", None),
]


# ---------------------------------------------------------------------------
# Access control and small helpers
# ---------------------------------------------------------------------------


def _login_redirect(request):
    login_url = reverse("staff_login")
    return redirect(f"{login_url}?{urlencode({'next': request.get_full_path()})}")


def _workspace_gate(view, allowed_roles):
    """Shared role gate for master-only and employee-only pages."""

    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return _login_redirect(request)

        role = get_staff_role(request.user)
        if role is None:
            messages.error(request, "This account does not have workspace access.")
            return redirect("staff_login")

        if allowed_roles is not None and role not in allowed_roles:
            if role == StaffProfile.ROLE_EMPLOYEE:
                messages.error(request, "That area is for the shop owner.")
                return redirect("staff_my_work")
            messages.error(request, "That page is part of the employee workspace.")
            return redirect("staff_dashboard")

        request.staff_role = role
        return view(request, *args, **kwargs)

    return never_cache(wrapped)


def workspace_required(view):
    """Require either a master or an employee workspace account."""

    return _workspace_gate(view, None)


def master_required(view):
    """Require the shop owner account."""

    return _workspace_gate(view, {StaffProfile.ROLE_MASTER})


def employee_required(view):
    """Require an employee account."""

    return _workspace_gate(view, {StaffProfile.ROLE_EMPLOYEE})


# Every existing request, review, story, analytics and export page is
# master-only. Keeping the old name makes that intent explicit in this file.
staff_required = master_required


def _display_name(user):
    return (user.get_full_name() or user.get_username() or "there").strip()


def _greeting():
    hour = timezone.localtime().hour
    if hour < 12:
        return "Good morning"
    if hour < 18:
        return "Good afternoon"
    return "Good evening"


def _format_datetime(value):
    if not value:
        return ""
    local = timezone.localtime(value)
    return local.strftime("%b %-d, %Y · %-I:%M %p")


def _format_date(value):
    if not value:
        return "Not set"
    return date_format(value, "M j, Y")


def _status_class(status):
    return {
        "new": "is-new",
        "contacted": "is-active",
        "reviewed": "is-active",
        "quoted": "is-active",
        "booked": "is-good",
        "confirmed": "is-good",
        "completed": "is-good",
        "closed": "is-muted",
        "declined": "is-bad",
    }.get(status, "is-muted")


def _ticket_status_class(status):
    return {
        WorkTicket.STATUS_ASSIGNED: "is-new",
        WorkTicket.STATUS_IN_PROGRESS: "is-active",
        WorkTicket.STATUS_COMPLETED: "is-good",
        WorkTicket.STATUS_CANCELLED: "is-muted",
    }.get(status, "is-muted")


def _ticket_counts(queryset=None):
    tickets = queryset if queryset is not None else WorkTicket.objects.all()
    week_ago = timezone.now() - timedelta(days=7)
    return {
        "assigned": tickets.filter(status=WorkTicket.STATUS_ASSIGNED).count(),
        "in_progress": tickets.filter(status=WorkTicket.STATUS_IN_PROGRESS).count(),
        "completed_week": tickets.filter(
            status=WorkTicket.STATUS_COMPLETED,
            completed_at__gte=week_ago,
        ).count(),
        "overdue": tickets.filter(
            status__in=WorkTicket.OPEN_STATUSES,
            due_date__lt=timezone.localdate(),
        ).count(),
    }


def _yes_no(value):
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    return {"yes": "Yes", "no": "No", "unsure": "Not sure"}.get((value or "").lower(), value or "Not answered")


def _csv_safe(value):
    """Stop spreadsheet apps from treating a customer field as a formula."""
    text = "" if value is None else str(value)
    if text[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text


def _new_counts():
    return {
        "callbacks": CallbackRequest.objects.filter(status="new").count(),
        "bookings": BookingRequest.objects.filter(status="new").count(),
        "claims": ClaimIntake.objects.filter(status="new").count(),
        "photos": PhotoRequest.objects.filter(status="new").count(),
    }


def _lead_summary(kind, obj):
    if kind == "callback":
        return obj.service_needed or "General enquiry"
    if kind == "booking":
        return f"{obj.vehicle} · {_format_date(obj.preferred_date)} · {obj.preferred_window}"
    if kind == "claim":
        claim = obj.claim_number or "No claim number yet"
        return f"{claim} · {obj.damage_description[:70] if obj.damage_description else 'MPI question'}"
    if kind == "photo":
        return f"{obj.vehicle} · {obj.damage_type} · {obj.photos.count()} photo{'s' if obj.photos.count() != 1 else ''}"
    return ""


def _detail_fields(kind, obj):
    if kind == "callback":
        return [
            ("Phone", obj.phone_number, "tel"),
            ("Best time to call", obj.preferred_time, "text"),
            ("Service needed", obj.service_needed, "text"),
            ("Vehicle or notes", obj.vehicle_description or "None provided", "text"),
            ("Source page", obj.source_page or "Unknown", "text"),
        ]
    if kind == "booking":
        return [
            ("Phone", obj.phone_number, "tel"),
            ("Email", obj.email or "Not provided", "email"),
            ("Vehicle", obj.vehicle, "text"),
            ("Service", obj.service, "text"),
            ("Preferred date", _format_date(obj.preferred_date), "text"),
            ("Preferred window", obj.preferred_window, "text"),
            ("Visit type", obj.get_visit_type_display(), "text"),
            ("Notes", obj.notes or "None provided", "text"),
        ]
    if kind == "claim":
        return [
            ("Phone", obj.phone_number, "tel"),
            ("Email", obj.email or "Not provided", "email"),
            ("MPI claim number", obj.claim_number or "Not provided", "text"),
            ("Has a claim", _yes_no(obj.has_claim), "text"),
            ("Anyone injured", _yes_no(obj.anyone_injured), "text"),
            ("Vehicle drivable", _yes_no(obj.vehicle_drivable), "text"),
            ("Registered owner", _yes_no(obj.registered_owner), "text"),
            ("Best time to call", obj.preferred_time or "Any time", "text"),
            ("Damage description", obj.damage_description or "None provided", "text"),
            ("Navigator summary", obj.result_summary or "Not captured", "text"),
        ]
    if kind == "photo":
        return [
            ("Phone", obj.phone_number, "tel"),
            ("Email", obj.email or "Not provided", "email"),
            ("Vehicle", obj.vehicle, "text"),
            ("Damage type", obj.damage_type, "text"),
            ("Best time to call", obj.preferred_time or "Any time", "text"),
            ("Description", obj.description or "None provided", "text"),
            ("Privacy consent", "Yes" if obj.privacy_consent else "No", "text"),
            ("Retention date", _format_date(obj.retention_expires_at), "text"),
        ]
    return []


def _filtered_leads(request, config):
    queryset = config["model"].objects.all()
    status = (request.GET.get("status") or "").strip()
    valid_statuses = {value for value, _label in config["model"].STATUS_CHOICES}
    if status in valid_statuses:
        queryset = queryset.filter(status=status)

    query = (request.GET.get("q") or "").strip()
    if query:
        lookup = Q()
        for field in config["search_fields"]:
            lookup |= Q(**{f"{field}__icontains": query})
        queryset = queryset.filter(lookup)
    return queryset


def _base_query(request):
    params = request.GET.copy()
    params.pop("page", None)
    return params.urlencode()


def _status_tabs(request, choices, counts, total):
    active_status = (request.GET.get("status") or "")
    params = request.GET.copy()
    params.pop("page", None)
    params.pop("status", None)
    query = params.urlencode()
    tabs = [
        {
            "value": "",
            "label": "All",
            "count": total,
            "active": active_status == "",
            "url": f"?{query}" if query else "?",
        }
    ]
    for value, label in choices:
        tabs.append(
            {
                "value": value,
                "label": label,
                "count": counts.get(value, 0),
                "active": active_status == value,
                "url": f"?{query}&status={value}" if query else f"?status={value}",
            }
        )
    return tabs, active_status


def _staff_context(request, nav, page_title, **extra):
    role = getattr(request, "staff_role", None) or get_staff_role(request.user)
    context = {
        "nav": nav,
        "page_title": page_title,
        "staff_user": request.user,
        "staff_role": role,
        "staff_is_master": role == StaffProfile.ROLE_MASTER,
        "staff_is_employee": role == StaffProfile.ROLE_EMPLOYEE,
        "staff_role_label": "Shop owner" if role == StaffProfile.ROLE_MASTER else "Employee",
        "nav_items": NAV_ITEMS,
        "content_items": CONTENT_ITEMS,
    }
    context.update(extra)
    return context


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


@never_cache
def staff_login(request):
    if request.user.is_authenticated:
        role = get_staff_role(request.user)
        if role:
            return redirect(workspace_home_name(request.user))

    next_url = request.POST.get("next") or request.GET.get("next") or ""
    form = StaffAuthenticationForm(request=request, data=request.POST or None)

    if request.method == "POST":
        if _login_blocked(request):
            form.add_error(
                None,
                "Too many sign-in attempts. Wait 15 minutes, then try again.",
            )
        elif form.is_valid():
            user = form.get_user()
            if not get_staff_role(user):
                form.add_error(
                    None,
                    "This account does not have workspace access. Ask the shop owner to add you on the Team page.",
                )
                _record_login_failure(request)
            else:
                _clear_login_failures(request)
                login(request, user)
                messages.success(request, f"Signed in as {_display_name(user)}.")
                if next_url and url_has_allowed_host_and_scheme(
                    next_url,
                    allowed_hosts={request.get_host()},
                    require_https=request.is_secure(),
                ):
                    return redirect(next_url)
                return redirect(workspace_home_name(user))
        else:
            _record_login_failure(request)

    return render(
        request,
        "staff/login.html",
        {
            "form": form,
            "next": next_url,
            "page_title": "Staff sign in",
        },
    )


@require_POST
def staff_logout(request):
    logout(request)
    messages.success(request, "You have been signed out.")
    return redirect("staff_login")


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@staff_required
def staff_dashboard(request):
    today = timezone.localdate()
    now = timezone.localtime()
    counts = _new_counts()

    attention = []
    for kind, config in LEAD_CONFIG.items():
        for obj in config["model"].objects.filter(status="new").order_by("-created_at")[:3]:
            attention.append(
                {
                    "kind": kind,
                    "label": config["label"],
                    "icon": config["icon"],
                    "reference": obj.reference,
                    "name": obj.full_name,
                    "phone": obj.phone_number,
                    "summary": _lead_summary(kind, obj),
                    "created_at": obj.created_at,
                    "url": reverse(config["detail_url"], args=[obj.pk]),
                }
            )
    attention.sort(key=lambda item: item["created_at"], reverse=True)

    upcoming = (
        BookingRequest.objects.filter(preferred_date__gte=today)
        .exclude(status__in=[BookingRequest.STATUS_DECLINED, BookingRequest.STATUS_COMPLETED])
        .order_by("preferred_date", "preferred_window")[:6]
    )

    week_ago = timezone.now() - timedelta(days=7)
    week_events = AnalyticsEvent.objects.filter(created_at__gte=week_ago)
    week_page_views = week_events.filter(name="page_view").count()
    week_leads = (
        CallbackRequest.objects.filter(created_at__gte=week_ago).count()
        + BookingRequest.objects.filter(created_at__gte=week_ago).count()
        + ClaimIntake.objects.filter(created_at__gte=week_ago).count()
        + PhotoRequest.objects.filter(created_at__gte=week_ago).count()
    )
    top_pages = list(
        week_events.filter(name="page_view")
        .exclude(path="")
        .values("path")
        .annotate(count=Count("id"))
        .order_by("-count")[:4]
    )

    email_backend = ""
    try:
        email_backend = settings.MAILERS["default"]["BACKEND"]
    except Exception:
        email_backend = ""
    email_configured = email_backend.endswith("smtp.EmailBackend")

    ticket_counts = _ticket_counts()
    shop_floor = (
        WorkTicket.objects.filter(status__in=WorkTicket.OPEN_STATUSES)
        .select_related("assignee")
        .order_by(F("due_date").asc(nulls_last=True), "created_at")[:5]
    )

    stock_parts = list(low_stock_parts())
    stock_value = sum(
        (part.stock_value for part in Part.objects.filter(is_active=True)),
        Decimal("0.00"),
    )

    context = _staff_context(
        request,
        "dashboard",
        "Dashboard",
        counts=counts,
        total_new=sum(counts.values()),
        attention=attention[:7],
        upcoming=upcoming,
        today=today,
        now=now,
        greeting=_greeting(),
        display_name=_display_name(request.user),
        week_page_views=week_page_views,
        week_leads=week_leads,
        top_pages=top_pages,
        published_reviews=Review.objects.filter(is_published=True).count(),
        total_reviews=Review.objects.count(),
        public_stories=RepairStory.objects.filter(is_published=True, customer_permission=True).count(),
        total_stories=RepairStory.objects.count(),
        ticket_counts=ticket_counts,
        shop_floor=shop_floor,
        email_configured=email_configured,
        debug_mode=settings.DEBUG,
        stock_parts=stock_parts[:5],
        stock_low_count=len(stock_parts),
        stock_critical_count=sum(1 for part in stock_parts if part.is_critical),
        stock_value=stock_value,
        stock_used_week=usage_since(timezone.now() - timedelta(days=7)),
        stock_part_count=Part.objects.filter(is_active=True).count(),
    )
    return render(request, "staff/dashboard.html", context)


# ---------------------------------------------------------------------------
# Lead lists and details
# ---------------------------------------------------------------------------


@staff_required
def staff_lead_list(request, kind):
    config = LEAD_CONFIG[kind]
    queryset = _filtered_leads(request, config)
    paginator = Paginator(queryset, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    rows = []
    for obj in page_obj.object_list:
        rows.append(
            {
                "obj": obj,
                "reference": obj.reference,
                "name": obj.full_name,
                "phone": obj.phone_number,
                "summary": _lead_summary(kind, obj),
                "status": obj.status,
                "status_label": obj.get_status_display(),
                "status_class": _status_class(obj.status),
                "created_at": obj.created_at,
                "created_label": _format_datetime(obj.created_at),
                "url": reverse(config["detail_url"], args=[obj.pk]),
            }
        )

    status_counts = {value: 0 for value, _label in config["model"].STATUS_CHOICES}
    for row in config["model"].objects.values("status").annotate(total=Count("id")):
        if row["status"] in status_counts:
            status_counts[row["status"]] = row["total"]

    total_count = config["model"].objects.count()
    active_status = (request.GET.get("status") or "")
    tab_params = request.GET.copy()
    tab_params.pop("page", None)
    tab_params.pop("status", None)
    tab_query = tab_params.urlencode()
    status_tabs = [
        {
            "value": "",
            "label": "All",
            "count": total_count,
            "active": active_status == "",
            "url": f"?{tab_query}" if tab_query else "?",
        }
    ]
    for value, label in config["model"].STATUS_CHOICES:
        status_tabs.append(
            {
                "value": value,
                "label": label,
                "count": status_counts.get(value, 0),
                "active": active_status == value,
                "url": f"?{tab_query}&status={value}" if tab_query else f"?status={value}",
            }
        )

    export_params = request.GET.copy()
    export_params.pop("page", None)
    export_query = export_params.urlencode()

    context = _staff_context(
        request,
        config["nav"],
        config["plural"],
        kind=kind,
        config=config,
        rows=rows,
        page_obj=page_obj,
        status_tabs=status_tabs,
        statuses=config["model"].STATUS_CHOICES,
        status_counts=status_counts,
        total_count=total_count,
        active_status=active_status,
        query=(request.GET.get("q") or ""),
        base_query=_base_query(request),
        export_url=reverse("staff_lead_export", args=[kind]) + (f"?{export_query}" if export_query else ""),
    )
    return render(request, "staff/leads_list.html", context)


@staff_required
def staff_lead_detail(request, kind, pk):
    config = LEAD_CONFIG[kind]
    obj = get_object_or_404(config["model"], pk=pk)
    form_class = config["form"]

    if request.method == "POST":
        if request.POST.get("action") == "delete":
            if kind == "photo":
                for photo in obj.photos.all():
                    if photo.image:
                        photo.image.delete(save=False)
            obj.delete()
            messages.success(request, f"{config['label']} {obj.reference} was deleted.")
            return redirect(config["list_url"])
        form = form_class(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, "The request was updated.")
            return redirect(config["detail_url"], pk=obj.pk)
        messages.error(request, "Please fix the highlighted fields.")
    else:
        form = form_class(instance=obj)

    photos = list(obj.photos.all()) if kind == "photo" else []
    work_tickets = (
        list(obj.work_tickets.select_related("assignee").order_by("-created_at"))
        if kind == "booking"
        else []
    )

    context = _staff_context(
        request,
        config["nav"],
        config["label"],
        kind=kind,
        config=config,
        lead=obj,
        form=form,
        detail_fields=_detail_fields(kind, obj),
        photos=photos,
        work_tickets=work_tickets,
        work_create_url=f"{reverse('staff_work_create')}?{urlencode({'booking': obj.pk})}",
        status_class=_status_class(obj.status),
        created_label=_format_datetime(obj.created_at),
        updated_label=_format_datetime(obj.updated_at),
        back_url=config["list_url"],
        delete_url=reverse(config["detail_url"], args=[obj.pk]),
    )
    return render(request, "staff/lead_detail.html", context)


@staff_required
def staff_lead_export(request, kind):
    config = LEAD_CONFIG[kind]
    queryset = _filtered_leads(request, config)

    response = HttpResponse(content_type="text/csv")
    filename = f"maple-leaf-{kind}-requests.csv"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow(
        [
            "Reference",
            "Received",
            "Name",
            "Phone",
            "Email",
            "Status",
            "Summary",
            "Internal notes",
        ]
    )
    for obj in queryset:
        writer.writerow(
            [
                obj.reference,
                _format_datetime(obj.created_at),
                _csv_safe(obj.full_name),
                _csv_safe(obj.phone_number),
                _csv_safe(getattr(obj, "email", "") or ""),
                obj.get_status_display(),
                _csv_safe(_lead_summary(kind, obj)),
                _csv_safe(obj.internal_notes or ""),
            ]
        )
    return response


@require_POST
@staff_required
def staff_photo_image_delete(request, pk):
    photo = get_object_or_404(PhotoRequestImage, pk=pk)
    request_id = photo.request_id
    if photo.image:
        photo.image.delete(save=False)
    photo.delete()
    messages.success(request, "The photo was deleted.")
    return redirect("staff_photo_detail", pk=request_id)


# ---------------------------------------------------------------------------
# Work tickets (master)
# ---------------------------------------------------------------------------


@staff_required
def staff_work_list(request):
    base = WorkTicket.objects.select_related("assignee", "booking")
    status = (request.GET.get("status") or "").strip()
    valid_statuses = {value for value, _label in WorkTicket.STATUS_CHOICES}
    if status not in valid_statuses:
        status = ""

    employee_filter = (request.GET.get("employee") or "").strip()
    if employee_filter.isdigit():
        base = base.filter(assignee_id=int(employee_filter))
    else:
        employee_filter = ""

    query = (request.GET.get("q") or "").strip()
    if query:
        base = base.filter(
            Q(reference__icontains=query)
            | Q(work_type__icontains=query)
            | Q(vehicle__icontains=query)
            | Q(customer_name__icontains=query)
            | Q(customer_phone__icontains=query)
            | Q(assignee__first_name__icontains=query)
            | Q(assignee__last_name__icontains=query)
            | Q(assignee__username__icontains=query)
            | Q(booking__reference__icontains=query)
        )

    status_counts = {
        value: base.filter(status=value).count()
        for value, _label in WorkTicket.STATUS_CHOICES
    }
    total_count = base.count()
    status_tabs, active_status = _status_tabs(
        request,
        WorkTicket.STATUS_CHOICES,
        status_counts,
        total_count,
    )

    queryset = base.filter(status=status) if status else base
    paginator = Paginator(queryset, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    rows = [
        {
            "ticket": ticket,
            "reference": ticket.reference,
            "work_type": ticket.work_type,
            "vehicle": ticket.vehicle,
            "assignee": ticket.assignee.get_full_name() or ticket.assignee.get_username(),
            "customer": ticket.customer_name or "No customer name",
            "due_label": _format_date(ticket.due_date) if ticket.due_date else "No due date",
            "status_label": ticket.get_status_display(),
            "status_class": _ticket_status_class(ticket.status),
            "created_label": _format_datetime(ticket.created_at),
            "url": reverse("staff_work_detail", args=[ticket.pk]),
            "is_overdue": ticket.is_overdue,
        }
        for ticket in page_obj.object_list
    ]

    context = _staff_context(
        request,
        "work",
        "Work tickets",
        rows=rows,
        page_obj=page_obj,
        status_tabs=status_tabs,
        active_status=active_status,
        total_count=total_count,
        status_counts=status_counts,
        query=query,
        employee_filter=employee_filter,
        employees=employee_users().order_by("first_name", "last_name", "username"),
        base_query=_base_query(request),
        counts=_ticket_counts(),
    )
    return render(request, "staff/work_list.html", context)


@staff_required
def staff_work_create(request):
    booking = None
    booking_id = request.GET.get("booking") or request.POST.get("booking")
    if booking_id:
        booking = get_object_or_404(BookingRequest, pk=booking_id)

    initial = {}
    if booking:
        initial = {
            "work_type": booking.service,
            "vehicle": booking.vehicle,
            "customer_name": booking.full_name,
            "customer_phone": booking.phone_number,
        }

    if request.method == "POST":
        form = WorkTicketForm(request.POST)
        if form.is_valid():
            ticket = form.save(commit=False)
            ticket.booking = booking
            ticket.created_by = request.user
            ticket.save()
            messages.success(
                request,
                f"Work ticket {ticket.reference} was assigned to "
                f"{ticket.assignee.get_full_name() or ticket.assignee.get_username()}.",
            )
            return redirect("staff_work_detail", pk=ticket.pk)
        messages.error(request, "Please fix the highlighted fields.")
    else:
        form = WorkTicketForm(initial=initial)

    context = _staff_context(
        request,
        "work",
        "New work ticket",
        form=form,
        booking=booking,
        is_new=True,
        has_employees=employee_users().exists(),
    )
    return render(request, "staff/work_form.html", context)


@staff_required
def staff_work_detail(request, pk):
    ticket = get_object_or_404(
        WorkTicket.objects.select_related("assignee", "booking", "created_by"),
        pk=pk,
    )
    context = _staff_context(
        request,
        "work",
        "Work ticket",
        ticket=ticket,
        status_class=_ticket_status_class(ticket.status),
        created_label=_format_datetime(ticket.created_at),
        started_label=_format_datetime(ticket.started_at),
        completed_label=_format_datetime(ticket.completed_at),
        updated_label=_format_datetime(ticket.updated_at),
        can_edit=ticket.is_open,
        parts_rows=ticket_part_rows(ticket),
        parts_total=ticket_parts_total(ticket),
        can_add_parts=True,
    )
    return render(request, "staff/work_detail.html", context)


@staff_required
def staff_work_edit(request, pk):
    ticket = get_object_or_404(
        WorkTicket.objects.select_related("assignee", "booking"),
        pk=pk,
    )
    if not ticket.is_open:
        messages.error(request, "Reopen this ticket before changing it.")
        return redirect("staff_work_detail", pk=ticket.pk)

    old_assignee_id = ticket.assignee_id
    old_assignee_name = ticket.assignee.get_full_name() or ticket.assignee.get_username()

    if request.method == "POST":
        form = WorkTicketForm(request.POST, instance=ticket)
        if form.is_valid():
            saved = form.save(commit=False)
            reassigned = saved.assignee_id != old_assignee_id
            if reassigned:
                saved.status = WorkTicket.STATUS_ASSIGNED
                saved.started_at = None
                saved.completed_at = None
            saved.save()
            if reassigned:
                new_name = saved.assignee.get_full_name() or saved.assignee.get_username()
                messages.success(
                    request,
                    f"{saved.reference} was reassigned from {old_assignee_name} to {new_name} "
                    "and reset to Assigned.",
                )
            else:
                messages.success(request, f"Work ticket {saved.reference} was updated.")
            return redirect("staff_work_detail", pk=saved.pk)
        messages.error(request, "Please fix the highlighted fields.")
    else:
        form = WorkTicketForm(instance=ticket)

    context = _staff_context(
        request,
        "work",
        "Edit work ticket",
        form=form,
        booking=ticket.booking,
        ticket=ticket,
        is_new=False,
        has_employees=employee_users().exists(),
    )
    return render(request, "staff/work_form.html", context)


@require_POST
@staff_required
def staff_work_cancel(request, pk):
    with transaction.atomic():
        ticket = get_object_or_404(
            WorkTicket.objects.select_for_update(),
            pk=pk,
        )
        if not ticket.is_open:
            messages.warning(request, "Only assigned or in-progress tickets can be cancelled.")
        else:
            ticket.status = WorkTicket.STATUS_CANCELLED
            ticket.save(update_fields=["status", "updated_at"])
            messages.success(request, f"Work ticket {ticket.reference} was cancelled.")
    return redirect("staff_work_detail", pk=pk)


@require_POST
@staff_required
def staff_work_reopen(request, pk):
    with transaction.atomic():
        ticket = get_object_or_404(
            WorkTicket.objects.select_for_update(),
            pk=pk,
        )
        if ticket.status not in (WorkTicket.STATUS_COMPLETED, WorkTicket.STATUS_CANCELLED):
            messages.warning(request, "This ticket is already open.")
        else:
            ticket.status = WorkTicket.STATUS_ASSIGNED
            ticket.started_at = None
            ticket.completed_at = None
            ticket.save(
                update_fields=["status", "started_at", "completed_at", "updated_at"]
            )
            messages.success(
                request,
                f"Work ticket {ticket.reference} was reopened and reset to Assigned.",
            )
    return redirect("staff_work_detail", pk=pk)


# ---------------------------------------------------------------------------
# Team (master)
# ---------------------------------------------------------------------------


def _employee_or_404(pk):
    return get_object_or_404(
        get_user_model().objects.select_related("staff_profile"),
        pk=pk,
        staff_profile__role=StaffProfile.ROLE_EMPLOYEE,
    )


@staff_required
def staff_team_list(request):
    employees = (
        get_user_model()
        .objects.filter(staff_profile__role=StaffProfile.ROLE_EMPLOYEE)
        .select_related("staff_profile")
        .annotate(
            open_ticket_count=Count(
                "work_tickets",
                filter=Q(work_tickets__status__in=WorkTicket.OPEN_STATUSES),
            )
        )
        .order_by("first_name", "last_name", "username")
    )
    context = _staff_context(
        request,
        "team",
        "Team",
        employees=employees,
        active_count=employees.filter(is_active=True).count(),
        total_count=employees.count(),
    )
    return render(request, "staff/team_list.html", context)


@staff_required
def staff_team_create(request):
    if request.method == "POST":
        form = EmployeeCreateForm(request.POST)
        if form.is_valid():
            employee = form.save()
            messages.success(
                request,
                f"Employee account “{employee.get_username()}” was created. "
                "Share the username and password with them directly.",
            )
            return redirect("staff_team")
        messages.error(request, "Please fix the highlighted fields.")
    else:
        form = EmployeeCreateForm()

    context = _staff_context(
        request,
        "team",
        "Add employee",
        form=form,
        is_new=True,
    )
    return render(request, "staff/team_form.html", context)


@staff_required
def staff_team_edit(request, pk):
    employee = _employee_or_404(pk)
    if request.method == "POST":
        form = StaffProfileForm(request.POST, instance=employee)
        if form.is_valid():
            form.save()
            messages.success(request, "Employee details were updated.")
            return redirect("staff_team")
        messages.error(request, "Please fix the highlighted fields.")
    else:
        form = StaffProfileForm(instance=employee)

    context = _staff_context(
        request,
        "team",
        "Edit employee",
        form=form,
        employee=employee,
        is_new=False,
    )
    return render(request, "staff/team_form.html", context)


@staff_required
def staff_team_password(request, pk):
    employee = _employee_or_404(pk)
    if request.method == "POST":
        form = EmployeeSetPasswordForm(employee, request.POST)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                f"Password reset for {employee.get_full_name() or employee.get_username()}.",
            )
            return redirect("staff_team")
        messages.error(request, "Please fix the highlighted fields.")
    else:
        form = EmployeeSetPasswordForm(employee)

    context = _staff_context(
        request,
        "team",
        "Reset employee password",
        form=form,
        employee=employee,
    )
    return render(request, "staff/team_password.html", context)


@require_POST
@staff_required
def staff_team_toggle(request, pk):
    employee = _employee_or_404(pk)
    if employee.is_active:
        open_count = WorkTicket.objects.filter(
            assignee=employee,
            status__in=WorkTicket.OPEN_STATUSES,
        ).count()
        if open_count:
            messages.warning(
                request,
                f"{employee.get_full_name() or employee.get_username()} still has "
                f"{open_count} open work ticket{'s' if open_count != 1 else ''}. "
                "Reassign or complete them before deactivating the account.",
            )
            return redirect("staff_team")
        employee.is_active = False
        employee.save(update_fields=["is_active"])
        messages.success(
            request,
            f"{employee.get_full_name() or employee.get_username()} can no longer sign in.",
        )
    else:
        employee.is_active = True
        employee.save(update_fields=["is_active"])
        messages.success(
            request,
            f"{employee.get_full_name() or employee.get_username()} can sign in again.",
        )
    return redirect("staff_team")


# ---------------------------------------------------------------------------
# Customer accounts (master only)
# ---------------------------------------------------------------------------


def _customer_or_404(pk):
    return get_object_or_404(
        get_user_model().objects.select_related("customer_profile"),
        pk=pk,
        customer_profile__isnull=False,
    )


def _customer_request_count(customer):
    return (
        customer.callback_requests.count()
        + customer.claim_intakes.count()
        + customer.booking_requests.count()
        + customer.photo_requests.count()
    )


@staff_required
def staff_customers(request):
    customers = list(
        get_user_model()
        .objects.filter(customer_profile__isnull=False)
        .select_related("customer_profile")
        .order_by("first_name", "last_name", "username")
    )
    for customer in customers:
        customer.request_count = _customer_request_count(customer)
    context = _staff_context(
        request,
        "customers",
        "Customers",
        customers=customers,
        active_count=sum(1 for customer in customers if customer.is_active),
        total_count=len(customers),
    )
    return render(request, "staff/customers.html", context)


@staff_required
def staff_customer_create(request):
    if request.method == "POST":
        form = CustomerCreateForm(request.POST)
        if form.is_valid():
            customer = form.save()
            linked = link_customer_requests(customer.customer_profile)
            message = (
                f"Customer account “{customer.get_username()}” was created. "
                "Share the username and password with them directly."
            )
            if linked:
                message += f" {linked} matching request{'s' if linked != 1 else ''} linked."
            messages.success(request, message)
            return redirect("staff_customers")
        messages.error(request, "Please fix the highlighted fields.")
    else:
        form = CustomerCreateForm()

    context = _staff_context(
        request,
        "customers",
        "Add customer",
        form=form,
        is_new=True,
    )
    return render(request, "staff/customer_form.html", context)


@staff_required
def staff_customer_edit(request, pk):
    customer = _customer_or_404(pk)
    if request.method == "POST":
        form = CustomerProfileForm(request.POST, instance=customer)
        if form.is_valid():
            form.save()
            linked = link_customer_requests(customer.customer_profile)
            message = "Customer details were updated."
            if linked:
                message += f" {linked} matching request{'s' if linked != 1 else ''} linked."
            messages.success(request, message)
            return redirect("staff_customers")
        messages.error(request, "Please fix the highlighted fields.")
    else:
        form = CustomerProfileForm(instance=customer)

    context = _staff_context(
        request,
        "customers",
        "Edit customer",
        form=form,
        customer=customer,
        request_count=_customer_request_count(customer),
    )
    return render(request, "staff/customer_form.html", context)


@staff_required
def staff_customer_password(request, pk):
    customer = _customer_or_404(pk)
    if request.method == "POST":
        form = EmployeeSetPasswordForm(customer, request.POST)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                f"Password reset for {customer.get_full_name() or customer.get_username()}.",
            )
            return redirect("staff_customers")
        messages.error(request, "Please fix the highlighted fields.")
    else:
        form = EmployeeSetPasswordForm(customer)

    context = _staff_context(
        request,
        "customers",
        "Reset customer password",
        form=form,
        customer=customer,
    )
    return render(request, "staff/customer_password.html", context)


@require_POST
@staff_required
def staff_customer_toggle(request, pk):
    customer = _customer_or_404(pk)
    if customer.is_active:
        customer.is_active = False
        customer.save(update_fields=["is_active"])
        messages.success(
            request,
            f"{customer.get_full_name() or customer.get_username()} can no longer sign in.",
        )
    else:
        customer.is_active = True
        customer.save(update_fields=["is_active"])
        messages.success(
            request,
            f"{customer.get_full_name() or customer.get_username()} can sign in again.",
        )
    return redirect("staff_customers")


# ---------------------------------------------------------------------------
# My work (employee)
# ---------------------------------------------------------------------------


@employee_required
def staff_my_work(request):
    base = WorkTicket.objects.filter(assignee=request.user).select_related("booking")
    status = (request.GET.get("status") or "").strip()
    valid_statuses = {value for value, _label in WorkTicket.STATUS_CHOICES}
    if status not in valid_statuses:
        status = ""

    status_counts = {
        value: base.filter(status=value).count()
        for value, _label in WorkTicket.STATUS_CHOICES
    }
    total_count = base.count()
    status_tabs, active_status = _status_tabs(
        request,
        WorkTicket.STATUS_CHOICES,
        status_counts,
        total_count,
    )

    queryset = base.filter(status=status) if status else base
    paginator = Paginator(queryset, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    rows = [
        {
            "ticket": ticket,
            "reference": ticket.reference,
            "work_type": ticket.work_type,
            "vehicle": ticket.vehicle,
            "due_label": _format_date(ticket.due_date) if ticket.due_date else "No due date",
            "status_label": ticket.get_status_display(),
            "status_class": _ticket_status_class(ticket.status),
            "url": reverse("staff_my_work_detail", args=[ticket.pk]),
            "is_overdue": ticket.is_overdue,
        }
        for ticket in page_obj.object_list
    ]

    context = _staff_context(
        request,
        "my_work",
        "My work",
        rows=rows,
        page_obj=page_obj,
        status_tabs=status_tabs,
        active_status=active_status,
        total_count=total_count,
        counts=status_counts,
        base_query=_base_query(request),
        assigned_count=status_counts.get(WorkTicket.STATUS_ASSIGNED, 0),
        in_progress_count=status_counts.get(WorkTicket.STATUS_IN_PROGRESS, 0),
        completed_count=status_counts.get(WorkTicket.STATUS_COMPLETED, 0),
        greeting=_greeting(),
        display_name=_display_name(request.user),
    )
    return render(request, "staff/my_work.html", context)


@employee_required
def staff_my_work_detail(request, pk):
    ticket = get_object_or_404(
        WorkTicket.objects.select_related("assignee", "booking", "created_by"),
        pk=pk,
        assignee=request.user,
    )

    if request.method == "POST":
        action = request.POST.get("action")

        if action in ("start", "complete"):
            with transaction.atomic():
                locked = get_object_or_404(
                    WorkTicket.objects.select_for_update(),
                    pk=pk,
                    assignee=request.user,
                )
                if action == "start":
                    if locked.status != WorkTicket.STATUS_ASSIGNED:
                        messages.warning(
                            request,
                            "This ticket can only be started while it is Assigned.",
                        )
                    else:
                        locked.status = WorkTicket.STATUS_IN_PROGRESS
                        locked.started_at = timezone.now()
                        locked.save(
                            update_fields=["status", "started_at", "updated_at"]
                        )
                        messages.success(
                            request,
                            f"You started {locked.reference}. Take your time and add notes as you go.",
                        )
                else:
                    if locked.status != WorkTicket.STATUS_IN_PROGRESS:
                        messages.warning(
                            request,
                            "Start the ticket first, then mark it complete.",
                        )
                    else:
                        now = timezone.now()
                        locked.status = WorkTicket.STATUS_COMPLETED
                        locked.started_at = locked.started_at or now
                        locked.completed_at = now
                        locked.save(
                            update_fields=[
                                "status",
                                "started_at",
                                "completed_at",
                                "updated_at",
                            ]
                        )
                        messages.success(
                            request,
                            f"{locked.reference} is complete. The shop owner can reopen it if anything is missed.",
                        )
            return redirect("staff_my_work_detail", pk=pk)

        if action == "save_note":
            if ticket.status == WorkTicket.STATUS_CANCELLED:
                messages.error(request, "This ticket was cancelled. Ask the shop owner to reopen it.")
                return redirect("staff_my_work_detail", pk=pk)
            form = WorkTicketNoteForm(request.POST, instance=ticket)
            if form.is_valid():
                form.save()
                messages.success(request, "Your work notes were saved.")
                return redirect("staff_my_work_detail", pk=pk)
            messages.error(request, "Please fix the highlighted field.")
        else:
            messages.error(request, "That action was not understood.")
            form = WorkTicketNoteForm(instance=ticket)
    else:
        form = WorkTicketNoteForm(instance=ticket)

    context = _staff_context(
        request,
        "my_work",
        "Work ticket",
        ticket=ticket,
        note_form=form,
        status_class=_ticket_status_class(ticket.status),
        created_label=_format_datetime(ticket.created_at),
        started_label=_format_datetime(ticket.started_at),
        completed_label=_format_datetime(ticket.completed_at),
        can_start=ticket.status == WorkTicket.STATUS_ASSIGNED,
        can_complete=ticket.status == WorkTicket.STATUS_IN_PROGRESS,
        can_note=ticket.status != WorkTicket.STATUS_CANCELLED,
        parts_rows=ticket_part_rows(ticket),
        can_add_parts=ticket.status != WorkTicket.STATUS_CANCELLED,
    )
    return render(request, "staff/my_work_detail.html", context)


# ---------------------------------------------------------------------------
# Stockroom
# ---------------------------------------------------------------------------

INVENTORY_CSV_COLUMNS = [
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
    "opening_stock",
    "reorder_level",
    "reorder_target",
    "is_critical",
    "notes",
]

CATEGORY_LOOKUP = {value.lower(): value for value, _label in Part.CATEGORY_CHOICES}
CATEGORY_LOOKUP.update({label.lower(): value for value, label in Part.CATEGORY_CHOICES})
UNIT_LOOKUP = {value.lower(): value for value, _label in Part.UNIT_CHOICES}
UNIT_LOOKUP.update({label.lower(): value for value, label in Part.UNIT_CHOICES})
BOOL_TRUE = {"1", "true", "yes", "y", "x"}


def _part_queryset():
    return Part.objects.select_related("supplier")


def _get_part(request, pk, active_only=False):
    queryset = _part_queryset()
    if active_only or not is_master(request.user):
        queryset = queryset.filter(is_active=True)
    return get_object_or_404(queryset, pk=pk)


def _allowed_tickets(request):
    if is_master(request.user):
        return (
            WorkTicket.objects.exclude(status=WorkTicket.STATUS_CANCELLED)
            .select_related("assignee")
            .order_by("-created_at")
        )
    return WorkTicket.objects.filter(
        assignee=request.user,
        status__in=WorkTicket.OPEN_STATUSES,
    ).order_by("-created_at")


def _ticket_redirect(request, ticket):
    if is_master(request.user):
        return redirect("staff_work_detail", pk=ticket.pk)
    return redirect("staff_my_work_detail", pk=ticket.pk)


def _add_validation_error(form, exc):
    messages_list = getattr(exc, "messages", None)
    form.add_error(None, messages_list[0] if messages_list else str(exc))


def _inventory_stats():
    active = Part.objects.filter(is_active=True)
    stock_value = sum((part.stock_value for part in active), Decimal("0.00"))
    return {
        "active_total": active.count(),
        "low_total": low_stock_count(),
        "out_total": active.filter(quantity_on_hand__lte=0).count(),
        "critical_total": active.filter(is_critical=True).count(),
        "uncounted_total": active.filter(last_counted_at__isnull=True).count(),
        "archived_total": Part.objects.filter(is_active=False).count(),
        "all_total": Part.objects.count(),
        "stock_value": stock_value,
    }


def _csv_header(value):
    return (value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _csv_int(value, default=0):
    text = str(value or "").strip()
    if not text:
        return default
    return int(text)


def _looks_true(value):
    return str(value or "").strip().lower() in BOOL_TRUE


def parse_inventory_csv(upload):
    """Parse an uploaded parts CSV into clean rows plus row-level errors."""

    upload.seek(0)
    try:
        text = io.TextIOWrapper(upload.file, encoding="utf-8-sig", newline="")
        reader = csv.DictReader(text)
        fieldnames = reader.fieldnames or []
    except Exception:
        return [], ["That file could not be read as CSV."]

    if not fieldnames:
        return [], ["The file has no header row."]

    index = {_csv_header(name): name for name in fieldnames}
    missing = [column for column in ("sku", "name") if column not in index]
    if missing:
        return [], [f"Missing required column(s): {', '.join(missing)}."]

    rows = []
    errors = []

    for line_number, raw in enumerate(reader, start=2):
        def value(column):
            source = index.get(column)
            return (raw.get(source) or "").strip() if source else ""

        sku = value("sku").upper()
        name = value("name")
        if not sku and not name:
            continue

        row_errors = []
        if not sku:
            row_errors.append("SKU is required.")
        if not name:
            row_errors.append("Name is required.")

        category_raw = value("category").lower()
        category = CATEGORY_LOOKUP.get(category_raw, Part.CATEGORY_OTHER)
        if category_raw and category_raw not in CATEGORY_LOOKUP:
            row_errors.append(f"Unknown category “{value('category')}”.")

        unit_raw = value("unit").lower()
        unit = UNIT_LOOKUP.get(unit_raw, Part.UNIT_EACH)
        if unit_raw and unit_raw not in UNIT_LOOKUP:
            row_errors.append(f"Unknown unit “{value('unit')}”.")

        try:
            cost_price = Decimal(value("cost_price") or "0").quantize(Decimal("0.01"))
            if cost_price < 0:
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            row_errors.append("Cost must be a number, for example 12.50.")
            cost_price = Decimal("0.00")

        try:
            opening_stock = _csv_int(value("opening_stock"), 0)
            reorder_level = _csv_int(value("reorder_level"), 0)
            reorder_target = _csv_int(value("reorder_target"), 0)
            if min(opening_stock, reorder_level, reorder_target) < 0:
                raise ValueError
        except ValueError:
            row_errors.append("Stock and reorder quantities must be whole numbers of 0 or more.")
            opening_stock = reorder_level = reorder_target = 0

        if reorder_level and not reorder_target:
            row_errors.append("Restock target is required when a reorder level is set.")
        elif reorder_target and reorder_target < reorder_level:
            row_errors.append("Restock target must be at least the reorder level.")

        if row_errors:
            errors.append(f"Row {line_number}: " + " ".join(row_errors))
            continue

        rows.append(
            {
                "line": line_number,
                "sku": sku,
                "name": name,
                "category": category,
                "brand": value("brand"),
                "part_number": value("part_number").upper(),
                "barcode": value("barcode"),
                "bin_location": value("bin_location").upper(),
                "unit": unit,
                "supplier": value("supplier"),
                "cost_price": f"{cost_price:.2f}",
                "opening_stock": opening_stock,
                "reorder_level": reorder_level,
                "reorder_target": reorder_target,
                "is_critical": _looks_true(value("is_critical")),
                "notes": value("notes"),
            }
        )

        if len(rows) >= 2000:
            errors.append("Only the first 2,000 rows can be imported at once. Split the file.")
            break

    return rows, errors


def _apply_inventory_rows(rows, user, create_missing_suppliers=True):
    created = 0
    updated = 0
    with transaction.atomic():
        for row in rows:
            line = row.get("line", "?")
            supplier = None
            supplier_name = (row.get("supplier") or "").strip()
            if supplier_name:
                supplier = Supplier.objects.filter(name__iexact=supplier_name).first()
                if not supplier and create_missing_suppliers:
                    supplier = Supplier.objects.create(name=supplier_name)
                if not supplier:
                    raise ValidationError(
                        f"Row {line}: supplier “{supplier_name}” does not exist."
                    )

            values = {
                "name": (row.get("name") or "").strip(),
                "category": row.get("category") or Part.CATEGORY_OTHER,
                "brand": (row.get("brand") or "").strip(),
                "part_number": (row.get("part_number") or "").strip().upper(),
                "barcode": (row.get("barcode") or "").strip(),
                "bin_location": (row.get("bin_location") or "").strip().upper(),
                "unit": row.get("unit") or Part.UNIT_EACH,
                "supplier": supplier,
                "cost_price": Decimal(str(row.get("cost_price") or "0")),
                "reorder_level": int(row.get("reorder_level") or 0),
                "reorder_target": int(row.get("reorder_target") or 0),
                "is_critical": bool(row.get("is_critical")),
                "notes": (row.get("notes") or "").strip(),
            }
            if not values["name"]:
                raise ValidationError(f"Row {line}: name is required.")

            part = Part.objects.filter(sku__iexact=row.get("sku", "")).first()
            if part:
                for field, value in values.items():
                    setattr(part, field, value)
                part.save()
                updated += 1
            else:
                part = Part.objects.create(
                    sku=(row.get("sku") or "").strip().upper(),
                    quantity_on_hand=0,
                    **values,
                )
                created += 1
                opening_stock = int(row.get("opening_stock") or 0)
                if opening_stock:
                    record_movement(
                        part,
                        StockMovement.KIND_COUNT,
                        opening_stock,
                        user=user,
                        reason="Opening stock from CSV import",
                    )
    return created, updated


@workspace_required
def staff_parts(request):
    can_manage = is_master(request.user)
    base = _part_queryset()

    show = (request.GET.get("show") or "active").strip()
    if show not in {"active", "low", "critical", "uncounted", "archived", "all"}:
        show = "active"

    if not can_manage:
        show = "active"
        base = base.filter(is_active=True)
    elif show == "archived":
        base = base.filter(is_active=False)
    elif show == "all":
        pass
    else:
        base = base.filter(is_active=True)
        if show == "low":
            base = base.filter(reorder_level__gt=0, quantity_on_hand__lte=F("reorder_level"))
        elif show == "critical":
            base = base.filter(is_critical=True)
        elif show == "uncounted":
            base = base.filter(last_counted_at__isnull=True)

    query = (request.GET.get("q") or "").strip()
    if query:
        base = base.filter(
            Q(sku__icontains=query)
            | Q(name__icontains=query)
            | Q(part_number__icontains=query)
            | Q(barcode__icontains=query)
            | Q(bin_location__icontains=query)
            | Q(brand__icontains=query)
            | Q(supplier__name__icontains=query)
        )

    category_filter = (request.GET.get("category") or "").strip()
    valid_categories = {value for value, _label in Part.CATEGORY_CHOICES}
    if category_filter not in valid_categories:
        category_filter = ""
    if category_filter:
        base = base.filter(category=category_filter)

    supplier_filter = (request.GET.get("supplier") or "").strip()
    if supplier_filter.isdigit():
        base = base.filter(supplier_id=int(supplier_filter))
    else:
        supplier_filter = ""

    ticket = None
    ticket_id = (request.GET.get("ticket") or "").strip()
    if ticket_id.isdigit():
        ticket = _allowed_tickets(request).filter(pk=int(ticket_id)).first()
        if not ticket:
            messages.error(request, "That work ticket is not available for parts.")
            return redirect("staff_parts")

    paginator = Paginator(base.order_by("name"), 25)
    page_obj = paginator.get_page(request.GET.get("page"))
    stats = _inventory_stats()

    context = _staff_context(
        request,
        "parts",
        "Parts",
        rows=page_obj.object_list,
        page_obj=page_obj,
        query=query,
        show=show,
        category_filter=category_filter,
        supplier_filter=supplier_filter,
        categories=Part.CATEGORY_CHOICES,
        suppliers=Supplier.objects.filter(is_active=True).order_by("name"),
        ticket=ticket,
        can_manage=can_manage,
        base_query=_base_query(request),
        **stats,
    )
    return render(request, "staff/inventory_list.html", context)


@workspace_required
def staff_part_detail(request, pk):
    part = _get_part(request, pk)
    can_manage = is_master(request.user)
    if can_manage:
        movements = (
            part.movements.select_related("created_by", "work_ticket")
            .order_by("-created_at", "-id")[:50]
        )
    else:
        movements = (
            part.movements.filter(created_by=request.user)
            .select_related("work_ticket")
            .order_by("-created_at", "-id")[:20]
        )
    context = _staff_context(
        request,
        "parts",
        part.name,
        part=part,
        movements=movements,
        can_manage=can_manage,
        stock_value=part.stock_value if can_manage else None,
    )
    return render(request, "staff/part_detail.html", context)


@staff_required
def staff_part_create(request):
    initial = {}
    supplier_id = (request.GET.get("supplier") or "").strip()
    if supplier_id.isdigit():
        initial["supplier"] = supplier_id

    if request.method == "POST":
        form = PartForm(request.POST)
        if form.is_valid():
            part = form.save()
            messages.success(
                request,
                f"{part.sku} was added. Record opening stock with Receive or Count.",
            )
            return redirect("staff_part_detail", pk=part.pk)
        messages.error(request, "Please fix the highlighted fields.")
    else:
        form = PartForm(initial=initial)

    context = _staff_context(
        request,
        "parts",
        "New part",
        form=form,
        is_new=True,
    )
    return render(request, "staff/part_form.html", context)


@staff_required
def staff_part_edit(request, pk):
    part = get_object_or_404(Part, pk=pk)
    if request.method == "POST":
        form = PartForm(request.POST, instance=part)
        if form.is_valid():
            part = form.save()
            messages.success(request, f"{part.sku} was updated.")
            return redirect("staff_part_detail", pk=part.pk)
        messages.error(request, "Please fix the highlighted fields.")
    else:
        form = PartForm(instance=part)

    context = _staff_context(
        request,
        "parts",
        f"Edit {part.sku}",
        form=form,
        part=part,
        is_new=False,
    )
    return render(request, "staff/part_form.html", context)


@require_POST
@staff_required
def staff_part_toggle(request, pk):
    part = get_object_or_404(Part, pk=pk)
    part.is_active = not part.is_active
    part.save(update_fields=["is_active", "updated_at"])
    if part.is_active:
        messages.success(request, f"{part.sku} is active again.")
    else:
        messages.success(request, f"{part.sku} was archived. Its history is kept.")
    return redirect("staff_part_detail", pk=part.pk)


@staff_required
def staff_part_receive(request, pk):
    part = _get_part(request, pk, active_only=True)
    if request.method == "POST":
        form = ReceiveStockForm(request.POST, part=part)
        if form.is_valid():
            try:
                movement = record_movement(
                    part,
                    StockMovement.KIND_RECEIVE,
                    form.cleaned_data["quantity"],
                    user=request.user,
                    reason=form.cleaned_data["note"],
                    unit_cost=form.cleaned_data["unit_cost"],
                )
            except ValidationError as exc:
                _add_validation_error(form, exc)
            else:
                messages.success(
                    request,
                    f"Received {movement.quantity_delta} {part.get_unit_display().lower()} "
                    f"of {part.name}. {part.quantity_on_hand} now on the shelf.",
                )
                return redirect("staff_part_detail", pk=part.pk)
        messages.error(request, "Please fix the highlighted fields.")
    else:
        form = ReceiveStockForm(part=part)

    context = _staff_context(
        request,
        "parts",
        "Receive stock",
        part=part,
        form=form,
        can_manage=True,
    )
    return render(request, "staff/stock_receive.html", context)


@workspace_required
def staff_part_use(request, pk):
    part = _get_part(request, pk, active_only=True)
    tickets = _allowed_tickets(request)

    initial = {}
    ticket_id = (request.GET.get("ticket") or "").strip()
    if ticket_id.isdigit():
        selected = tickets.filter(pk=int(ticket_id)).first()
        if selected:
            initial["ticket"] = selected
        else:
            messages.warning(request, "That ticket is not open for parts on this account.")

    if request.method == "POST":
        form = UseStockForm(request.POST, part=part, tickets=tickets)
        if form.is_valid():
            ticket = form.cleaned_data.get("ticket")
            try:
                movement = record_movement(
                    part,
                    StockMovement.KIND_USE,
                    form.cleaned_data["quantity"],
                    user=request.user,
                    ticket=ticket,
                    reason=form.cleaned_data["note"],
                )
            except ValidationError as exc:
                _add_validation_error(form, exc)
            else:
                used = abs(movement.quantity_delta)
                messages.success(
                    request,
                    f"Took {used} {part.get_unit_display().lower()} of {part.name} "
                    f"from bin {part.bin_location or 'not set'}."
                    + (f" Linked to {ticket.reference}." if ticket else ""),
                )
                if ticket:
                    return _ticket_redirect(request, ticket)
                return redirect("staff_part_detail", pk=part.pk)
        messages.error(request, "Please fix the highlighted fields.")
    else:
        form = UseStockForm(part=part, tickets=tickets, initial=initial)

    context = _staff_context(
        request,
        "parts",
        "Use stock",
        part=part,
        form=form,
        ticket=initial.get("ticket"),
        can_manage=is_master(request.user),
    )
    return render(request, "staff/stock_use.html", context)


@staff_required
def staff_part_count(request, pk):
    part = _get_part(request, pk, active_only=True)
    if request.method == "POST":
        form = CountStockForm(request.POST, part=part)
        if form.is_valid():
            counted = form.cleaned_data["counted_quantity"]
            reason = dict(COUNT_REASONS)[form.cleaned_data["reason"]]
            note = form.cleaned_data["note"]
            if note:
                reason = f"{reason} — {note}"
            if counted == part.quantity_on_hand:
                part.last_counted_at = timezone.now()
                part.save(update_fields=["last_counted_at", "updated_at"])
                messages.success(
                    request,
                    f"Count confirmed for {part.name}. No stock change was needed.",
                )
                return redirect("staff_part_detail", pk=part.pk)
            try:
                movement = record_movement(
                    part,
                    StockMovement.KIND_COUNT,
                    counted,
                    user=request.user,
                    reason=reason,
                )
            except ValidationError as exc:
                _add_validation_error(form, exc)
            else:
                messages.success(
                    request,
                    f"{part.name} counted at {counted}. "
                    f"Stock changed by {movement.quantity_delta:+d}.",
                )
                return redirect("staff_part_detail", pk=part.pk)
        messages.error(request, "Please fix the highlighted fields.")
    else:
        form = CountStockForm(part=part)

    context = _staff_context(
        request,
        "parts",
        "Count stock",
        part=part,
        form=form,
        can_manage=True,
    )
    return render(request, "staff/stock_count.html", context)


@staff_required
def staff_part_adjust(request, pk):
    part = _get_part(request, pk, active_only=True)
    if request.method == "POST":
        form = AdjustStockForm(request.POST)
        if form.is_valid():
            reason = dict(COUNT_REASONS)[form.cleaned_data["reason"]]
            note = form.cleaned_data["note"]
            if note:
                reason = f"{reason} — {note}"
            try:
                movement = record_movement(
                    part,
                    StockMovement.KIND_ADJUST,
                    form.cleaned_data["quantity"],
                    user=request.user,
                    reason=reason,
                )
            except ValidationError as exc:
                _add_validation_error(form, exc)
            else:
                messages.success(
                    request,
                    f"{part.name} adjusted by {movement.quantity_delta:+d}. "
                    f"{part.quantity_on_hand} now on the shelf.",
                )
                return redirect("staff_part_detail", pk=part.pk)
        messages.error(request, "Please fix the highlighted fields.")
    else:
        form = AdjustStockForm()

    context = _staff_context(
        request,
        "parts",
        "Adjust stock",
        part=part,
        form=form,
        can_manage=True,
    )
    return render(request, "staff/stock_adjust.html", context)


@require_POST
@staff_required
def staff_ticket_part_return(request, pk):
    ticket = get_object_or_404(WorkTicket, pk=pk)
    part = get_object_or_404(Part, pk=request.POST.get("part"))
    quantity = request.POST.get("quantity") or 1
    try:
        movement = record_movement(
            part,
            StockMovement.KIND_RETURN,
            quantity,
            user=request.user,
            ticket=ticket,
            reason=f"Returned from {ticket.reference}",
        )
    except ValidationError as exc:
        messages.error(request, getattr(exc, "messages", [str(exc)])[0])
    else:
        messages.success(
            request,
            f"Returned {movement.quantity_delta} {part.get_unit_display().lower()} "
            f"of {part.name} to the shelf.",
        )
    return redirect("staff_work_detail", pk=ticket.pk)


@staff_required
def staff_reorder(request):
    parts = list(low_stock_parts())
    groups = reorder_groups(parts)
    estimated_cost = sum((group["estimated_cost"] for group in groups), Decimal("0.00"))
    context = _staff_context(
        request,
        "reorder",
        "Reorder list",
        parts=parts,
        groups=groups,
        low_count=len(parts),
        critical_count=sum(1 for part in parts if part.is_critical),
        estimated_cost=estimated_cost,
    )
    return render(request, "staff/reorder_list.html", context)


@staff_required
def staff_reorder_export(request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="maple-leaf-reorder-list.csv"'
    writer = csv.writer(response)
    writer.writerow(
        [
            "SKU",
            "Part",
            "Bin",
            "On hand",
            "Reorder level",
            "Restock to",
            "Suggested order",
            "Unit",
            "Supplier",
            "Unit cost",
            "Estimated cost",
            "Critical",
        ]
    )
    for part in low_stock_parts():
        suggested = part.suggested_order_quantity
        writer.writerow(
            [
                _csv_safe(part.sku),
                _csv_safe(part.name),
                _csv_safe(part.bin_location),
                part.quantity_on_hand,
                part.reorder_level,
                part.reorder_target,
                suggested,
                part.get_unit_display(),
                _csv_safe(part.supplier.name if part.supplier else ""),
                f"{part.cost_price:.2f}",
                f"{suggested * part.cost_price:.2f}",
                "Yes" if part.is_critical else "No",
            ]
        )
    return response


@staff_required
def staff_bulk_receive(request):
    supplier_id = (request.GET.get("supplier") or request.POST.get("supplier") or "").strip()
    supplier = None
    if supplier_id.isdigit():
        supplier = get_object_or_404(Supplier, pk=int(supplier_id))

    parts = []
    if supplier:
        parts = list(
            Part.objects.filter(is_active=True, supplier=supplier).order_by(
                "bin_location", "name"
            )
        )

    if request.method == "POST" and supplier:
        received_lines = []
        try:
            for part in parts:
                raw = (request.POST.get(f"qty_{part.pk}") or "").strip()
                if not raw:
                    continue
                quantity = int(raw)
                if quantity < 0:
                    raise ValueError
                if quantity:
                    received_lines.append((part, quantity))
        except ValueError:
            messages.error(request, "Enter whole numbers of 0 or more.")
        else:
            if not received_lines:
                messages.info(request, "No quantities were entered.")
            else:
                try:
                    with transaction.atomic():
                        for part, quantity in received_lines:
                            record_movement(
                                part,
                                StockMovement.KIND_RECEIVE,
                                quantity,
                                user=request.user,
                                reason=f"Delivery received from {supplier.name}",
                            )
                except ValidationError as exc:
                    messages.error(request, getattr(exc, "messages", [str(exc)])[0])
                else:
                    units = sum(quantity for _part, quantity in received_lines)
                    messages.success(
                        request,
                        f"Received {units} unit{'s' if units != 1 else ''} "
                        f"across {len(received_lines)} line{'s' if len(received_lines) != 1 else ''}.",
                    )
                    return redirect(f"{reverse('staff_bulk_receive')}?supplier={supplier.pk}")

    context = _staff_context(
        request,
        "reorder",
        "Receive delivery",
        suppliers=Supplier.objects.filter(parts__is_active=True)
        .distinct()
        .order_by("name"),
        supplier=supplier,
        parts=parts,
    )
    return render(request, "staff/bulk_receive.html", context)


@staff_required
def staff_suppliers(request):
    suppliers = list(Supplier.objects.order_by("-is_active", "name"))
    for supplier in suppliers:
        supplier.active_parts = supplier.parts.filter(is_active=True).count()
        supplier.low_parts = supplier.parts.filter(
            is_active=True,
            reorder_level__gt=0,
            quantity_on_hand__lte=F("reorder_level"),
        ).count()

    context = _staff_context(
        request,
        "suppliers",
        "Suppliers",
        suppliers=suppliers,
        no_supplier_parts=Part.objects.filter(is_active=True, supplier__isnull=True).count(),
    )
    return render(request, "staff/supplier_list.html", context)


@staff_required
def staff_supplier_create(request):
    if request.method == "POST":
        form = SupplierForm(request.POST)
        if form.is_valid():
            supplier = form.save()
            messages.success(request, f"{supplier.name} was added.")
            return redirect("staff_suppliers")
        messages.error(request, "Please fix the highlighted fields.")
    else:
        form = SupplierForm()

    context = _staff_context(
        request,
        "suppliers",
        "New supplier",
        form=form,
        is_new=True,
    )
    return render(request, "staff/supplier_form.html", context)


@staff_required
def staff_supplier_edit(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk)
    if request.method == "POST":
        form = SupplierForm(request.POST, instance=supplier)
        if form.is_valid():
            supplier = form.save()
            messages.success(request, f"{supplier.name} was updated.")
            return redirect("staff_suppliers")
        messages.error(request, "Please fix the highlighted fields.")
    else:
        form = SupplierForm(instance=supplier)

    context = _staff_context(
        request,
        "suppliers",
        f"Edit {supplier.name}",
        form=form,
        supplier=supplier,
        is_new=False,
    )
    return render(request, "staff/supplier_form.html", context)


@require_POST
@staff_required
def staff_supplier_toggle(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk)
    supplier.is_active = not supplier.is_active
    supplier.save(update_fields=["is_active", "updated_at"])
    messages.success(
        request,
        f"{supplier.name} is {'active' if supplier.is_active else 'archived'}.",
    )
    return redirect("staff_suppliers")


@staff_required
def staff_inventory_export(request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="maple-leaf-parts.csv"'
    writer = csv.writer(response)
    writer.writerow(
        [
            "SKU",
            "Part",
            "Category",
            "Brand",
            "Part number",
            "Barcode",
            "Bin",
            "Unit",
            "Supplier",
            "Unit cost",
            "On hand",
            "Stock value",
            "Reorder level",
            "Restock to",
            "Critical",
            "Active",
            "Last counted",
            "Notes",
        ]
    )
    for part in _part_queryset().order_by("name"):
        writer.writerow(
            [
                _csv_safe(part.sku),
                _csv_safe(part.name),
                part.get_category_display(),
                _csv_safe(part.brand),
                _csv_safe(part.part_number),
                _csv_safe(part.barcode),
                _csv_safe(part.bin_location),
                part.get_unit_display(),
                _csv_safe(part.supplier.name if part.supplier else ""),
                f"{part.cost_price:.2f}",
                part.quantity_on_hand,
                f"{part.stock_value:.2f}",
                part.reorder_level,
                part.reorder_target,
                "Yes" if part.is_critical else "No",
                "Yes" if part.is_active else "No",
                part.last_counted_at.strftime("%Y-%m-%d") if part.last_counted_at else "",
                _csv_safe(part.notes),
            ]
        )
    return response


@staff_required
def staff_inventory_template(request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="maple-leaf-parts-template.csv"'
    writer = csv.writer(response)
    writer.writerow(INVENTORY_CSV_COLUMNS)
    writer.writerow(
        [
            "BP-1042",
            "3M Panel Bond 08115",
            "paint",
            "3M",
            "08115",
            "",
            "A-02-3",
            "each",
            "National Autobody Wholesalers",
            "42.50",
            "4",
            "1",
            "3",
            "yes",
            "Two-part panel adhesive.",
        ]
    )
    return response


@staff_required
def staff_inventory_import(request):
    form = InventoryImportForm(request.POST or None, request.FILES or None)
    preview_rows = []
    errors = []
    rows_json = ""
    create_missing_suppliers = request.POST.get("create_missing_suppliers") == "on"

    if request.method == "POST":
        action = request.POST.get("action", "preview")
        if action == "confirm":
            rows_json = request.POST.get("rows_json") or ""
            try:
                rows = json.loads(rows_json)
                if not isinstance(rows, list):
                    raise ValueError
            except (ValueError, TypeError):
                messages.error(request, "The import preview expired. Please choose the file again.")
            else:
                preview_rows = rows[:50]
                try:
                    created, updated = _apply_inventory_rows(
                        rows,
                        request.user,
                        create_missing_suppliers=create_missing_suppliers,
                    )
                except (ValidationError, InvalidOperation, ValueError) as exc:
                    message = getattr(exc, "messages", [str(exc)])[0]
                    messages.error(request, message)
                else:
                    messages.success(
                        request,
                        f"Import complete: {created} added, {updated} updated. "
                        "Existing stock levels were not overwritten.",
                    )
                    return redirect("staff_parts")
        else:
            if form.is_valid():
                preview_rows, errors = parse_inventory_csv(form.cleaned_data["csv_file"])
                if not preview_rows and not errors:
                    errors.append("No data rows were found in the file.")
                rows_json = json.dumps(preview_rows)
            else:
                messages.error(request, "Please choose a CSV file to preview.")

    context = _staff_context(
        request,
        "parts",
        "Import parts",
        form=form,
        preview_rows=preview_rows[:50],
        preview_count=len(preview_rows),
        errors=errors,
        rows_json=rows_json,
        create_missing_suppliers=create_missing_suppliers,
        columns=INVENTORY_CSV_COLUMNS,
    )
    return render(request, "staff/inventory_import.html", context)


# ---------------------------------------------------------------------------
# Reviews
# ---------------------------------------------------------------------------


@staff_required
def staff_reviews(request):
    context = _staff_context(
        request,
        "reviews",
        "Reviews",
        reviews=Review.objects.all(),
        published_count=Review.objects.filter(is_published=True).count(),
    )
    return render(request, "staff/reviews.html", context)


@staff_required
def staff_review_form(request, pk=None):
    review = get_object_or_404(Review, pk=pk) if pk else None
    if request.method == "POST":
        form = ReviewForm(request.POST, instance=review)
        if form.is_valid():
            saved = form.save()
            messages.success(request, f"Review by {saved.author} saved.")
            return redirect("staff_reviews")
        messages.error(request, "Please fix the highlighted fields.")
    else:
        form = ReviewForm(instance=review)

    context = _staff_context(
        request,
        "reviews",
        "Edit review" if review else "Add review",
        form=form,
        review=review,
        is_new=review is None,
    )
    return render(request, "staff/review_form.html", context)


@require_POST
@staff_required
def staff_review_toggle(request, pk):
    review = get_object_or_404(Review, pk=pk)
    review.is_published = not review.is_published
    review.save(update_fields=["is_published"])
    if review.is_published:
        messages.success(request, f"Review by {review.author} is now visible on the website.")
    else:
        messages.success(request, f"Review by {review.author} is hidden from the website.")
    return redirect("staff_reviews")


@require_POST
@staff_required
def staff_review_delete(request, pk):
    review = get_object_or_404(Review, pk=pk)
    author = review.author
    review.delete()
    messages.success(request, f"Review by {author} was deleted.")
    return redirect("staff_reviews")


# ---------------------------------------------------------------------------
# Repair stories
# ---------------------------------------------------------------------------


@staff_required
def staff_stories(request):
    context = _staff_context(
        request,
        "stories",
        "Repair stories",
        stories=RepairStory.objects.all(),
        published_count=RepairStory.objects.filter(is_published=True, customer_permission=True).count(),
    )
    return render(request, "staff/stories.html", context)


@staff_required
def staff_story_form(request, pk=None):
    story = get_object_or_404(RepairStory, pk=pk) if pk else None
    old_images = {}
    if story:
        for field in ("before_image", "after_image"):
            image = getattr(story, field)
            if image:
                old_images[field] = (image.name, image.storage)

    if request.method == "POST":
        form = RepairStoryForm(request.POST, request.FILES, instance=story)
        if form.is_valid():
            saved = form.save()
            for field, (old_name, storage) in old_images.items():
                new_image = getattr(saved, field)
                if new_image and new_image.name != old_name:
                    try:
                        storage.delete(old_name)
                    except Exception:
                        pass
            messages.success(request, f"Repair story “{saved.title}” saved.")
            return redirect("staff_stories")
        messages.error(request, "Please fix the highlighted fields.")
    else:
        form = RepairStoryForm(instance=story)

    context = _staff_context(
        request,
        "stories",
        "Edit repair story" if story else "Add repair story",
        form=form,
        story=story,
        is_new=story is None,
    )
    return render(request, "staff/story_form.html", context)


@require_POST
@staff_required
def staff_story_toggle(request, pk):
    story = get_object_or_404(RepairStory, pk=pk)
    if story.is_published:
        story.is_published = False
        story.save(update_fields=["is_published", "updated_at"])
        messages.success(request, f"“{story.title}” is hidden from the public gallery.")
    elif not story.customer_permission:
        messages.warning(
            request,
            "Add written customer permission before publishing this story. It is still saved as a private draft.",
        )
    else:
        story.is_published = True
        story.save(update_fields=["is_published", "updated_at"])
        messages.success(request, f"“{story.title}” is now visible on the public gallery.")
    return redirect("staff_stories")


@require_POST
@staff_required
def staff_story_delete(request, pk):
    story = get_object_or_404(RepairStory, pk=pk)
    title = story.title
    for field in ("before_image", "after_image"):
        image = getattr(story, field)
        if image:
            image.delete(save=False)
    story.delete()
    messages.success(request, f"Repair story “{title}” was deleted.")
    return redirect("staff_stories")


# ---------------------------------------------------------------------------
# Website activity
# ---------------------------------------------------------------------------


def _analytics_range(request):
    try:
        days = int(request.GET.get("days", 30))
    except (TypeError, ValueError):
        days = 30
    if days not in (7, 30, 90):
        days = 30
    return days


@staff_required
def staff_analytics(request):
    days = _analytics_range(request)
    start_day = timezone.localdate() - timedelta(days=days - 1)
    since = timezone.now() - timedelta(days=days - 1)
    events = AnalyticsEvent.objects.filter(created_at__gte=since)

    total_views = events.filter(name="page_view").count()
    sessions = events.exclude(session_key="").values("session_key").distinct().count()
    total_events = events.count()

    daily_lookup = {
        row["created_at__date"]: row["total"]
        for row in events.values("created_at__date").annotate(total=Count("id"))
    }
    daily = []
    max_daily = max(daily_lookup.values(), default=0)
    for offset in range(days):
        day = start_day + timedelta(days=offset)
        count = daily_lookup.get(day, 0)
        daily.append(
            {
                "date": day,
                "label": date_format(day, "M j"),
                "short": date_format(day, "j"),
                "count": count,
                "pct": max(3, round((count / max_daily) * 100)) if max_daily else 3,
            }
        )

    top_pages = list(
        events.filter(name="page_view")
        .values("path")
        .annotate(count=Count("id"))
        .order_by("-count")[:10]
    )
    max_page = max((row["count"] for row in top_pages), default=0)
    for row in top_pages:
        row["label"] = row["path"] or "/"
        row["pct"] = max(4, round((row["count"] / max_page) * 100)) if max_page else 4

    event_rows = []
    for row in events.values("name").annotate(count=Count("id")).order_by("-count"):
        event_rows.append(
            {
                "name": row["name"],
                "label": EVENT_LABELS.get(row["name"], row["name"].replace("_", " ").title()),
                "count": row["count"],
                "pct": max(4, round((row["count"] / total_events) * 100)) if total_events else 4,
            }
        )

    recent = list(events.select_related()[:20])
    for event in recent:
        event.human_name = EVENT_LABELS.get(event.name, event.name.replace("_", " ").title())
        event.display_time = _format_datetime(event.created_at)

    context = _staff_context(
        request,
        "analytics",
        "Website activity",
        days=days,
        start_day=start_day,
        total_views=total_views,
        sessions=sessions,
        total_events=total_events,
        daily=daily,
        max_daily=max_daily,
        top_pages=top_pages,
        event_rows=event_rows,
        recent=recent,
        export_url=reverse("staff_analytics_export") + f"?days={days}",
    )
    return render(request, "staff/analytics.html", context)


@staff_required
def staff_analytics_export(request):
    days = _analytics_range(request)
    since = timezone.now() - timedelta(days=days - 1)
    events = AnalyticsEvent.objects.filter(created_at__gte=since)

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="maple-leaf-activity-{days}-days.csv"'
    writer = csv.writer(response)
    writer.writerow(["Received", "Event", "Path", "Page title", "Referrer", "Session", "Metadata"])
    for event in events:
        try:
            metadata = json.dumps(event.metadata, ensure_ascii=False)
        except Exception:
            metadata = "{}"
        writer.writerow(
            [
                _format_datetime(event.created_at),
                event.name,
                _csv_safe(event.path),
                _csv_safe(event.page_title),
                _csv_safe(event.referrer),
                _csv_safe(event.session_key),
                _csv_safe(metadata),
            ]
        )
    return response


# ---------------------------------------------------------------------------
# Account
# ---------------------------------------------------------------------------


@workspace_required
def staff_account(request):
    if request.method == "POST":
        form = StaffProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Your account details were updated.")
            return redirect("staff_account")
        messages.error(request, "Please fix the highlighted fields.")
    else:
        form = StaffProfileForm(instance=request.user)

    context = _staff_context(
        request,
        "account",
        "My account",
        form=form,
        last_login_label=_format_datetime(request.user.last_login),
    )
    return render(request, "staff/account.html", context)


@workspace_required
def staff_password_change(request):
    if request.method == "POST":
        form = StaffPasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, "Your password was changed.")
            return redirect("staff_account")
        messages.error(request, "Please fix the highlighted fields.")
    else:
        form = StaffPasswordChangeForm(request.user)

    context = _staff_context(
        request,
        "account",
        "Change password",
        form=form,
    )
    return render(request, "staff/password_change.html", context)


# ---------------------------------------------------------------------------
# Estimator pricing (master only)
# ---------------------------------------------------------------------------


@staff_required
def staff_estimator(request):
    estimate_settings = EstimateSettings.load()
    services = list(EstimateService.objects.annotate(addon_count=Count("addons")))
    context = _staff_context(
        request,
        "estimator",
        "Repair estimator",
        services=services,
        estimate_settings=estimate_settings,
        priced_count=sum(1 for service in services if service.is_priced),
        enabled_count=sum(1 for service in services if service.enabled),
        addon_total=sum(service.addon_count for service in services),
    )
    return render(request, "staff/estimator.html", context)


@staff_required
def staff_estimate_edit(request, slug):
    service = get_object_or_404(EstimateService, slug=slug)
    if request.method == "POST":
        form = EstimateServiceForm(request.POST, instance=service)
        if form.is_valid():
            saved = form.save(commit=False)
            saved.updated_by = request.user
            saved.save()
            messages.success(request, f"{saved.title} estimate saved.")
            return redirect("staff_estimator")
        messages.error(request, "Please fix the highlighted fields.")
    else:
        form = EstimateServiceForm(instance=service)

    context = _staff_context(
        request,
        "estimator",
        f"Edit {service.title}",
        form=form,
        service=service,
        addons=service.addons.all(),
        addon_count=service.addons.count(),
    )
    return render(request, "staff/estimate_form.html", context)


@staff_required
def staff_estimate_addons(request, slug):
    service = get_object_or_404(EstimateService, slug=slug)
    if request.method == "POST":
        form = EstimateAddOnForm(request.POST)
        if form.is_valid():
            addon = form.save(commit=False)
            addon.service = service
            addon.save()
            messages.success(request, f"“{addon.label}” added to {service.title}.")
            return redirect("staff_estimate_addons", slug=service.slug)
        messages.error(request, "Please fix the highlighted fields.")
    else:
        form = EstimateAddOnForm(initial={"display_order": service.addons.count()})

    context = _staff_context(
        request,
        "estimator",
        f"{service.title} add-ons",
        service=service,
        addons=service.addons.all(),
        form=form,
    )
    return render(request, "staff/estimate_addons.html", context)


@staff_required
def staff_estimate_addon_edit(request, slug, pk):
    service = get_object_or_404(EstimateService, slug=slug)
    addon = get_object_or_404(EstimateAddOn, pk=pk, service=service)
    if request.method == "POST":
        form = EstimateAddOnForm(request.POST, instance=addon)
        if form.is_valid():
            saved = form.save()
            messages.success(request, f"“{saved.label}” updated.")
            return redirect("staff_estimate_addons", slug=service.slug)
        messages.error(request, "Please fix the highlighted fields.")
    else:
        form = EstimateAddOnForm(instance=addon)

    context = _staff_context(
        request,
        "estimator",
        f"Edit “{addon.label}”",
        service=service,
        addon=addon,
        form=form,
    )
    return render(request, "staff/estimate_addon_form.html", context)


@require_POST
@staff_required
def staff_estimate_addon_delete(request, slug, pk):
    service = get_object_or_404(EstimateService, slug=slug)
    addon = get_object_or_404(EstimateAddOn, pk=pk, service=service)
    label = addon.label
    addon.delete()
    messages.success(request, f"“{label}” was removed from {service.title}.")
    return redirect("staff_estimate_addons", slug=service.slug)


@staff_required
def staff_estimate_settings(request):
    estimate_settings = EstimateSettings.load()
    if request.method == "POST":
        form = EstimateSettingsForm(request.POST, instance=estimate_settings)
        if form.is_valid():
            saved = form.save(commit=False)
            saved.updated_by = request.user
            saved.save()
            messages.success(request, "Estimator settings saved.")
            return redirect("staff_estimator")
        messages.error(request, "Please fix the highlighted fields.")
    else:
        form = EstimateSettingsForm(instance=estimate_settings)

    context = _staff_context(
        request,
        "estimator",
        "Estimator settings",
        form=form,
        estimate_settings=estimate_settings,
    )
    return render(request, "staff/estimate_settings.html", context)
