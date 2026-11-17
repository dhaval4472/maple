import json
import logging
import re

from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from django.core.mail import send_mail
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .content import (
    CALLBACK_WINDOWS,
    REVIEWS,
    SERVICE_BY_SLUG,
    SERVICES,
    TOOLS,
    TOOL_BY_SLUG,
)
from .customer_access import customer_for_submission
from .estimating import money, price_estimate, starting_price
from .forms import BookingForm, ClaimIntakeForm, EstimateDetailsForm, PhotoRequestForm
from .housekeeping import maybe_prune_expired_photo_requests
from .images import optimize_photo_upload
from .models import (
    AnalyticsEvent,
    BookingRequest,
    CallbackRequest,
    ClaimIntake,
    EstimateService,
    EstimateSettings,
    PhotoRequest,
    PhotoRequestImage,
    RepairStory,
    Review,
)

SHOP_PHONE_DISPLAY = "(204) 586-8253"
SHOP_EMAIL = getattr(settings, "SHOP_EMAIL", "mapleleafautorepairs@gmail.com")
logger = logging.getLogger(__name__)
CALLBACK_TIME_VALUES = {value for value, _label in CALLBACK_WINDOWS}
ANALYTICS_ALLOWED = {
    "page_view",
    "cta_click",
    "callback_open",
    "callback_submit",
    "claim_navigator_start",
    "claim_navigator_complete",
    "claim_navigator_submit",
    "chip_checker_result",
    "chip_checker_submit",
    "repair_replace_result",
    "repair_replace_submit",
    "booking_start",
    "booking_submit",
    "photo_request_start",
    "photo_request_submit",
    "service_view",
    "tool_view",
    "phone_click",
    "gallery_view",
    "review_filter",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clean(value, limit=500):
    return (value or "").strip()[:limit]


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _rate_limited(request, bucket, limit=6, window=600):
    """Best-effort cache-based rate limit. Fails open if the cache is unavailable."""
    ip = _client_ip(request)
    if not ip:
        return False
    key = f"rate:{bucket}:{ip}"
    try:
        if cache.add(key, 1, window):
            return False
        count = cache.incr(key)
    except Exception:
        return False
    return count > limit


def _send_shop_email(subject, body):
    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None) or "noreply@mapleleafauto.ca",
            recipient_list=[SHOP_EMAIL],
            fail_silently=False,
        )
    except Exception:
        # The request is already stored in the admin; a mail outage should not
        # lose the lead or show the visitor an error.
        logger.exception("Could not send shop notification: %s", subject)


def _json_ld(data):
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _published_reviews():
    try:
        queryset = Review.objects.all()
        if not queryset.exists():
            return REVIEWS
        return list(queryset.filter(is_published=True))
    except Exception:
        return REVIEWS


def _meta(request):
    return {
        "ip_address": _client_ip(request),
        "user_agent": _clean(request.META.get("HTTP_USER_AGENT"), 300),
    }


def _source_page(request):
    return _clean(request.POST.get("source_page") or request.path, 160)


def _store_callback(details, request):
    return CallbackRequest.objects.create(
        full_name=details["full_name"],
        phone_number=details["phone_number"],
        customer=customer_for_submission(request.user, phone=details["phone_number"]),
        preferred_time=details["preferred_time"],
        service_needed=details["service_needed"],
        vehicle_description=details["vehicle_description"],
        source_page=_source_page(request),
        **_meta(request),
    )


def _callback_email(details, reference):
    body = (
        "New callback request from mapleleafauto.ca\n\n"
        f"Reference: {reference}\n"
        f"Name: {details['full_name']}\n"
        f"Phone: {details['phone_number']}\n"
        f"Preferred time: {details['preferred_time']}\n"
        f"Service needed: {details['service_needed']}\n"
        f"Vehicle/notes: {details['vehicle_description'] or 'None'}\n"
        f"Source: {details.get('source_page', '') or 'Unknown'}\n"
    )
    _send_shop_email("Maple Leaf Auto - Callback Request", body)


def _validate_callback(data):
    full_name = _clean(data.get("full_name"), 100)
    phone_number = _clean(data.get("phone_number"), 40)
    preferred_time = _clean(data.get("preferred_time"), 60) or "Anytime today"
    if preferred_time not in CALLBACK_TIME_VALUES:
        preferred_time = "Anytime today"
    service_needed = _clean(data.get("service_needed"), 140) or "General enquiry"
    vehicle_description = _clean(data.get("vehicle_description"), 1200)
    honeypot = _clean(data.get("website"), 100)

    errors = {}
    if not full_name:
        errors["full_name"] = "Please tell us your name."
    if not phone_number:
        errors["phone_number"] = "Please add a phone number so we can call you back."
    elif len(re.sub(r"\D", "", phone_number)) < 7:
        errors["phone_number"] = "That phone number looks too short. Please check it."

    return {
        "full_name": full_name,
        "phone_number": phone_number,
        "preferred_time": preferred_time,
        "service_needed": service_needed,
        "vehicle_description": vehicle_description,
        "honeypot": honeypot,
    }, errors


# ---------------------------------------------------------------------------
# Core pages
# ---------------------------------------------------------------------------


def home_view(request):
    reviews = _published_reviews()
    review_schema = {
        "@context": "https://schema.org",
        "@type": "AutoRepair",
        "name": "Maple Leaf Auto Body & Glass",
        "url": "https://mapleleafauto.ca/",
        "telephone": "+1-204-586-8253",
        "image": "https://mapleleafauto.ca/static/img/package/car-repair.webp",
        "address": {
            "@type": "PostalAddress",
            "streetAddress": "492 Dufferin Ave",
            "addressLocality": "Winnipeg",
            "addressRegion": "MB",
            "postalCode": "R2W 2Y6",
            "addressCountry": "CA",
        },
        "openingHoursSpecification": {
            "@type": "OpeningHoursSpecification",
            "dayOfWeek": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
            "opens": "09:00",
            "closes": "18:00",
        },
        "review": [
            {
                "@type": "Review",
                "author": {"@type": "Person", "name": review.author if hasattr(review, "author") else review["author"]},
                "reviewBody": review.quote if hasattr(review, "quote") else review["quote"],
                "reviewRating": {"@type": "Rating", "ratingValue": review.rating if hasattr(review, "rating") else review["rating"], "bestRating": 5},
            }
            for review in reviews
        ],
    }
    return render(
        request,
        "mapleleaf/home.html",
        {
            "reviews": reviews,
            "services": SERVICES,
            "tools": TOOLS,
            "review_schema": _json_ld(review_schema),
        },
    )


def services_view(request):
    return render(request, "mapleleaf/services.html", {"services": SERVICES})


def service_detail_view(request, slug):
    service = SERVICE_BY_SLUG.get(slug)
    if not service:
        raise Http404("Service not found")
    related_tools = [TOOL_BY_SLUG[slug] for slug in service.get("tools", []) if slug in TOOL_BY_SLUG]
    related_services = [item for item in SERVICES if item["category"] == service["category"] and item["slug"] != slug][:3]
    service_schema = {
        "@context": "https://schema.org",
        "@type": "Service",
        "name": service["title"],
        "serviceType": service["title"],
        "description": service["summary"],
        "url": f"https://mapleleafauto.ca/services/{service['slug']}/",
        "provider": {"@type": "AutoRepair", "name": "Maple Leaf Auto Body & Glass", "telephone": "+1-204-586-8253"},
        "areaServed": {"@type": "City", "name": "Winnipeg"},
    }
    faq_schema = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": question,
                "acceptedAnswer": {"@type": "Answer", "text": answer},
            }
            for question, answer in service["faqs"]
        ],
    }
    return render(
        request,
        "mapleleaf/service_detail.html",
        {
            "service": service,
            "related_tools": related_tools,
            "related_services": related_services,
            "service_schema": _json_ld(service_schema),
            "faq_schema": _json_ld(faq_schema),
        },
    )


def about_view(request):
    return render(request, "mapleleaf/about.html")


def contact_view(request):
    if request.method == "POST":
        is_ajax = request.headers.get("x-requested-with") == "XMLHttpRequest"
        details, errors = _validate_callback(request.POST)

        # Silently accept honeypot submissions so bots do not retry.
        if details["honeypot"]:
            if is_ajax:
                return JsonResponse({"ok": True, "message": "Thanks — we will be in touch."})
            messages.success(request, "Thanks — we will be in touch.")
            return redirect("contact")

        if errors:
            message = "Please fix the highlighted fields and try again."
            if is_ajax:
                return JsonResponse({"ok": False, "message": message, "errors": errors}, status=400)
            messages.error(request, message)
            return render(
                request,
                "mapleleaf/contact.html",
                {
                    "form_values": request.POST,
                    "field_errors": errors,
                },
            )

        if _rate_limited(request, "callback", limit=8, window=600):
            message = "Too many requests from this connection. Please call the shop instead."
            if is_ajax:
                return JsonResponse({"ok": False, "message": message, "errors": {}}, status=429)
            messages.error(request, message)
            return redirect("contact")

        callback = _store_callback(details, request)
        details["source_page"] = callback.source_page
        _callback_email(details, callback.reference)
        success_message = (
            f'Thanks {details["full_name"]} — your callback request is in '
            f'(reference {callback.reference}). We will call you during shop hours.'
        )
        if is_ajax:
            return JsonResponse({"ok": True, "message": success_message, "reference": callback.reference})
        messages.success(request, success_message)
        return redirect("contact")

    return render(request, "mapleleaf/contact.html")


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


def tools_view(request):
    return render(request, "mapleleaf/tools.html", {"tools": TOOLS})


def claim_navigator_view(request):
    success = None
    form = ClaimIntakeForm(request.POST or None)
    if request.method == "POST":
        if request.POST.get("website"):
            success = {"reference": "—", "honeypot": True}
        elif form.is_valid():
            if _rate_limited(request, "claim", limit=6, window=600):
                messages.error(request, "Too many requests from this connection. Please call the shop instead.")
            else:
                data = form.cleaned_data
                summary = _clean(data.get("result_summary"), 1200) or "Navigator completed without a stored summary."
                intake = ClaimIntake.objects.create(
                    full_name=data["full_name"],
                    phone_number=data["phone_number"],
                    email=data.get("email", ""),
                    customer=customer_for_submission(
                        request.user,
                        email=data.get("email", ""),
                        phone=data["phone_number"],
                    ),
                    claim_number=data.get("claim_number", ""),
                    has_claim=data.get("has_claim", ""),
                    anyone_injured=data.get("anyone_injured", ""),
                    vehicle_drivable=data.get("vehicle_drivable", ""),
                    registered_owner=data.get("registered_owner", ""),
                    damage_description=data.get("damage_description", ""),
                    preferred_time=data.get("preferred_time", "Anytime today"),
                    result_summary=summary,
                    **_meta(request),
                )
                _send_shop_email(
                    "Maple Leaf Auto - MPI Claim Navigator",
                    (
                        "New MPI claim navigator request\n\n"
                        f"Reference: {intake.reference}\n"
                        f"Name: {intake.full_name}\n"
                        f"Phone: {intake.phone_number}\n"
                        f"Email: {intake.email or 'None'}\n"
                        f"Claim number: {intake.claim_number or 'None'}\n"
                        f"Injured: {intake.anyone_injured or 'Not answered'}\n"
                        f"Drivable: {intake.vehicle_drivable or 'Not answered'}\n"
                        f"Registered owner: {intake.registered_owner or 'Not answered'}\n"
                        f"Preferred time: {intake.preferred_time}\n"
                        f"Damage: {intake.damage_description or 'None'}\n\n"
                        f"Navigator summary:\n{intake.result_summary}\n"
                    ),
                )
                success = {"reference": intake.reference}
        else:
            messages.error(request, "Please fix the highlighted fields and try again.")

    return render(
        request,
        "mapleleaf/claim_navigator.html",
        {"form": form, "success": success, "tool": TOOL_BY_SLUG["mpi-claim-navigator"]},
    )


def chip_checker_view(request):
    return render(
        request,
        "mapleleaf/chip_checker.html",
        {"tool": TOOL_BY_SLUG["windshield-chip-checker"]},
    )


def repair_or_replace_view(request):
    return render(
        request,
        "mapleleaf/repair_or_replace.html",
        {"tool": TOOL_BY_SLUG["repair-or-replace"]},
    )


def repair_estimate_view(request):
    """Two-step, anonymous repair estimator driven by master-set prices.

    Nothing is written to the database. The visitor either sees a range built
    from the shop's own numbers, an honest "call for pricing" state, or the MPI
    route when the work is an insurance claim.
    """
    estimate_settings = EstimateSettings.load()
    all_services = list(EstimateService.objects.order_by("display_order", "slug"))
    service_lookup = {service.slug: service for service in all_services}

    requested_slug = _clean(request.POST.get("service") or request.GET.get("service"), 40)
    service = service_lookup.get(requested_slug)

    def is_available(candidate):
        return bool(estimate_settings.site_enabled and candidate.is_priced)

    if requested_slug and service is None:
        messages.error(
            request,
            "That estimate is not available right now. Choose a service below or call the shop.",
        )
    elif service is not None and not is_available(service):
        messages.error(
            request,
            "That estimate is not live yet. Choose another service below or call the shop for pricing.",
        )
        service = None

    result = None
    mpi_route = False
    form = None
    addon_count = 0

    if service is not None:
        addon_count = service.addons.filter(enabled=True).count()
        if request.method == "POST":
            if request.POST.get("website"):
                return redirect("repair_estimate")
            if _rate_limited(request, "estimate", limit=40, window=600):
                messages.error(
                    request,
                    "Too many estimates from this connection. Please call the shop instead.",
                )
                return redirect("repair_estimate")

            form = EstimateDetailsForm(request.POST, service=service)
            if form.is_valid():
                if form.cleaned_data["claim_type"] == "mpi":
                    mpi_route = True
                else:
                    result = price_estimate(
                        service,
                        vehicle_class=form.cleaned_data["vehicle_class"],
                        severity=form.cleaned_data.get("severity") or "moderate",
                        addons=form.cleaned_data.get("addons") or (),
                        settings_obj=estimate_settings,
                    )
            else:
                messages.error(request, "Please check the highlighted choices and try again.")
        else:
            form = EstimateDetailsForm(service=service)

    tool_cards = []
    for item in all_services:
        available = is_available(item)
        floor = starting_price(item, settings_obj=estimate_settings) if available else None
        tool_cards.append(
            {
                "service": item,
                "available": available,
                "from_display": money(floor) if floor is not None else "",
            }
        )

    return render(
        request,
        "mapleleaf/repair_estimate.html",
        {
            "tool": TOOL_BY_SLUG["repair-estimate"],
            "estimate_settings": estimate_settings,
            "estimator_enabled": estimate_settings.site_enabled,
            "service": service,
            "form": form,
            "result": result,
            "mpi_route": mpi_route,
            "addon_count": addon_count,
            "tool_cards": tool_cards,
            "priced_count": sum(1 for card in tool_cards if card["available"]),
        },
    )


# ---------------------------------------------------------------------------
# Booking, photos, gallery, privacy
# ---------------------------------------------------------------------------


def booking_view(request):
    success = None
    form = BookingForm(request.POST or None)
    if request.method == "POST":
        if request.POST.get("website"):
            success = {"reference": "—"}
        elif form.is_valid():
            if _rate_limited(request, "booking", limit=5, window=900):
                messages.error(request, "Too many booking requests from this connection. Please call the shop.")
            else:
                data = form.cleaned_data
                booking = BookingRequest.objects.create(
                    full_name=data["full_name"],
                    phone_number=data["phone_number"],
                    email=data.get("email", ""),
                    customer=customer_for_submission(
                        request.user,
                        email=data.get("email", ""),
                        phone=data["phone_number"],
                    ),
                    vehicle=data["vehicle"],
                    service=data["service"],
                    preferred_date=data["preferred_date"],
                    preferred_window=data["preferred_window"],
                    visit_type=data["visit_type"],
                    notes=data.get("notes", ""),
                    privacy_consent=data["privacy_consent"],
                    **_meta(request),
                )
                _send_shop_email(
                    "Maple Leaf Auto - Booking Request",
                    (
                        "New preferred drop-off request\n\n"
                        f"Reference: {booking.reference}\n"
                        f"Name: {booking.full_name}\n"
                        f"Phone: {booking.phone_number}\n"
                        f"Email: {booking.email or 'None'}\n"
                        f"Vehicle: {booking.vehicle}\n"
                        f"Service: {booking.service}\n"
                        f"Preferred date: {booking.preferred_date}\n"
                        f"Preferred window: {booking.preferred_window}\n"
                        f"Visit type: {booking.get_visit_type_display()}\n"
                        f"Notes: {booking.notes or 'None'}\n\n"
                        "This is a request, not a confirmed appointment. Call the customer to confirm capacity.\n"
                    ),
                )
                success = booking
        else:
            messages.error(request, "Please fix the highlighted fields and try again.")

    return render(
        request,
        "mapleleaf/booking.html",
        {"form": form, "success": success, "services": SERVICES},
    )


def photo_request_view(request):
    success = None
    form = PhotoRequestForm(request.POST or None, request.FILES or None)
    if request.method == "POST":
        if request.POST.get("website"):
            success = {"reference": "—"}
        elif form.is_valid():
            if _rate_limited(request, "photos", limit=4, window=900):
                messages.error(request, "Too many photo requests from this connection. Please call the shop.")
            else:
                data = form.cleaned_data
                try:
                    optimized_photos = [optimize_photo_upload(photo) for photo in data["photos"]]
                except Exception:
                    optimized_photos = []
                    form.add_error(
                        "photos",
                        "One of the photos could not be prepared. Please try a different JPEG, PNG or WebP.",
                    )

                if optimized_photos:
                    photo_request = PhotoRequest(
                        full_name=data["full_name"],
                        phone_number=data["phone_number"],
                        email=data.get("email", ""),
                        customer=customer_for_submission(
                            request.user,
                            email=data.get("email", ""),
                            phone=data["phone_number"],
                        ),
                        vehicle=data["vehicle"],
                        damage_type=data["damage_type"],
                        description=data.get("description", ""),
                        preferred_time=data.get("preferred_time", "Anytime today"),
                        privacy_consent=data["privacy_consent"],
                        **_meta(request),
                    )
                    photo_request.set_retention()
                    photo_request.save()
                    for photo in optimized_photos:
                        PhotoRequestImage.objects.create(request=photo_request, image=photo)
                    _send_shop_email(
                        "Maple Leaf Auto - Photo Request",
                        (
                            "New damage photo request\n\n"
                            f"Reference: {photo_request.reference}\n"
                            f"Name: {photo_request.full_name}\n"
                            f"Phone: {photo_request.phone_number}\n"
                            f"Email: {photo_request.email or 'None'}\n"
                            f"Vehicle: {photo_request.vehicle}\n"
                            f"Damage type: {dict(PhotoRequestForm.DAMAGE_TYPES).get(photo_request.damage_type, photo_request.damage_type)}\n"
                            f"Preferred time: {photo_request.preferred_time}\n"
                            f"Description: {photo_request.description or 'None'}\n"
                            f"Photos: {photo_request.photos.count()}\n"
                            f"Consent: {'yes' if photo_request.privacy_consent else 'no'}\n"
                            f"Retention date: {photo_request.retention_expires_at}\n"
                        ),
                    )
                    success = photo_request
                    maybe_prune_expired_photo_requests()
        else:
            messages.error(request, "Please fix the highlighted fields and try again.")

    return render(
        request,
        "mapleleaf/photo_request.html",
        {
            "form": form,
            "success": success,
            "retention_days": getattr(settings, "PHOTO_RETENTION_DAYS", 365),
            "photo_limit": getattr(settings, "PHOTO_UPLOAD_MAX_FILES", 4),
            "photo_max_bytes": getattr(settings, "PHOTO_UPLOAD_MAX_BYTES", 6 * 1024 * 1024),
            "photo_max_mb": getattr(settings, "PHOTO_UPLOAD_MAX_BYTES", 6 * 1024 * 1024) // (1024 * 1024),
        },
    )


def repair_stories_view(request):
    stories = RepairStory.objects.filter(is_published=True, customer_permission=True)
    category = request.GET.get("category", "all")
    if category in {"body", "mechanical", "maintenance"}:
        stories = stories.filter(category=category)
    return render(
        request,
        "mapleleaf/repair_stories.html",
        {
            "stories": stories,
            "active_category": category if category in {"body", "mechanical", "maintenance"} else "all",
        },
    )


def privacy_view(request):
    return render(
        request,
        "mapleleaf/privacy.html",
        {
            "retention_days": getattr(settings, "PHOTO_RETENTION_DAYS", 365),
            "shop_email": SHOP_EMAIL,
            "phone_display": SHOP_PHONE_DISPLAY,
        },
    )


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


@require_POST
def analytics_event_view(request):
    if _rate_limited(request, "analytics", limit=180, window=60):
        return JsonResponse({"ok": False}, status=429)

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"ok": False, "error": "invalid JSON"}, status=400)

    if not isinstance(payload, dict):
        return JsonResponse({"ok": False, "error": "invalid payload"}, status=400)

    name = _clean(payload.get("name"), 80)
    if name not in ANALYTICS_ALLOWED:
        return JsonResponse({"ok": False, "error": "unknown event"}, status=400)

    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    try:
        metadata_json = json.dumps(metadata, ensure_ascii=False)
    except (TypeError, ValueError):
        metadata_json = "{}"
    if len(metadata_json) > 2000:
        metadata = {}
    else:
        metadata = json.loads(metadata_json)

    session = request.session.session_key
    if not session:
        request.session.create()
        session = request.session.session_key

    AnalyticsEvent.objects.create(
        name=name,
        path=_clean(payload.get("path"), 300),
        page_title=_clean(payload.get("title"), 200),
        referrer=_clean(payload.get("referrer"), 500),
        session_key=_clean(session, 64),
        metadata=metadata,
    )
    return JsonResponse({"ok": True})


# Backward-compatible names kept for any existing imports.
home = home_view
services = services_view
about = about_view
contact = contact_view
