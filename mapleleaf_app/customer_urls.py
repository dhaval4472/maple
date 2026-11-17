from django.urls import path

from . import customer_views

urlpatterns = [
    path("login/", customer_views.customer_login, name="customer_login"),
    path("logout/", customer_views.customer_logout, name="customer_logout"),
    path("", customer_views.customer_dashboard, name="customer_dashboard"),
    path("password/", customer_views.customer_password_change, name="customer_password_change"),
]
