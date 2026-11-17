from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path

from mapleleaf_app.sitemaps import ServiceSitemap, StaticViewSitemap

sitemaps = {
    "static": StaticViewSitemap,
    "services": ServiceSitemap,
}

urlpatterns = [
    path("admin/", admin.site.urls),
    path("staff/", include("mapleleaf_app.staff_urls")),
    path("account/", include("mapleleaf_app.customer_urls")),
    path("sitemap.xml", sitemap, {"sitemaps": sitemaps}, name="sitemap"),
    path("", include("mapleleaf_app.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
