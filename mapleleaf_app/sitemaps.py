from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from .content import SERVICES


class StaticViewSitemap(Sitemap):
    priority = 0.7
    changefreq = "monthly"

    def items(self):
        return [
            "home",
            "services",
            "tools",
            "claim_navigator",
            "chip_checker",
            "repair_or_replace",
            "booking",
            "photo_request",
            "repair_stories",
            "privacy",
            "about",
            "contact",
        ]

    def location(self, item):
        return reverse(item)


class ServiceSitemap(Sitemap):
    priority = 0.8
    changefreq = "monthly"

    def items(self):
        return [service["slug"] for service in SERVICES]

    def location(self, slug):
        return reverse("service_detail", kwargs={"slug": slug})
