from django.urls import path

from . import auth_views, views

urlpatterns = [
    path("", views.home_view, name="home"),
    path("login/", auth_views.sign_in, name="login"),
    path("services/", views.services_view, name="services"),
    path("services/<slug:slug>/", views.service_detail_view, name="service_detail"),
    path("tools/", views.tools_view, name="tools"),
    path("tools/repair-estimate/", views.repair_estimate_view, name="repair_estimate"),
    path("tools/mpi-claim-navigator/", views.claim_navigator_view, name="claim_navigator"),
    path("tools/windshield-chip-checker/", views.chip_checker_view, name="chip_checker"),
    path("tools/repair-or-replace/", views.repair_or_replace_view, name="repair_or_replace"),
    path("book/", views.booking_view, name="booking"),
    path("photos/request/", views.photo_request_view, name="photo_request"),
    path("repair-stories/", views.repair_stories_view, name="repair_stories"),
    path("privacy/", views.privacy_view, name="privacy"),
    path("analytics/event/", views.analytics_event_view, name="analytics_event"),
    path("about/", views.about_view, name="about"),
    path("contact/", views.contact_view, name="contact"),
]
