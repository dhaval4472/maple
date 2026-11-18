from django.contrib.sitemaps import Sitemap
from django.db.models import Count, Q
from django.urls import reverse

from .content import SERVICES
from .models import BlogCategory, BlogPost, BlogTag

PUBLISHED = Q(posts__status=BlogPost.STATUS_PUBLISHED)


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
            "blog",
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


class BlogPostSitemap(Sitemap):
    priority = 0.8
    changefreq = "weekly"

    def items(self):
        return BlogPost.objects.filter(status=BlogPost.STATUS_PUBLISHED)

    def location(self, post):
        return post.get_absolute_url()

    def lastmod(self, post):
        return post.updated_at


class BlogCategorySitemap(Sitemap):
    priority = 0.5
    changefreq = "monthly"

    def items(self):
        return BlogCategory.objects.annotate(
            published_count=Count("posts", filter=PUBLISHED, distinct=True)
        ).filter(published_count__gt=0).order_by("name")

    def location(self, category):
        return category.get_absolute_url()

    def lastmod(self, category):
        latest = category.posts.filter(
            status=BlogPost.STATUS_PUBLISHED
        ).order_by("-updated_at").first()
        return latest.updated_at if latest else None


class BlogTagSitemap(Sitemap):
    priority = 0.4
    changefreq = "monthly"

    def items(self):
        return BlogTag.objects.annotate(
            published_count=Count("posts", filter=PUBLISHED, distinct=True)
        ).filter(published_count__gt=0).order_by("name")

    def location(self, tag):
        return tag.get_absolute_url()
