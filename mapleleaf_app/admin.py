from django.contrib import admin

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


@admin.register(CallbackRequest)
class CallbackRequestAdmin(admin.ModelAdmin):
    list_display = ("reference", "full_name", "phone_number", "service_needed", "preferred_time", "status", "created_at")
    list_filter = ("status", "preferred_time", "created_at")
    search_fields = ("reference", "full_name", "phone_number", "service_needed", "vehicle_description")
    readonly_fields = ("reference", "created_at", "updated_at", "ip_address", "user_agent")
    date_hierarchy = "created_at"


@admin.register(ClaimIntake)
class ClaimIntakeAdmin(admin.ModelAdmin):
    list_display = ("reference", "full_name", "phone_number", "has_claim", "vehicle_drivable", "status", "created_at")
    list_filter = ("status", "has_claim", "anyone_injured", "vehicle_drivable", "created_at")
    search_fields = ("reference", "full_name", "phone_number", "claim_number", "damage_description")
    readonly_fields = ("reference", "created_at", "updated_at", "ip_address", "user_agent")
    date_hierarchy = "created_at"


@admin.register(BookingRequest)
class BookingRequestAdmin(admin.ModelAdmin):
    list_display = ("reference", "full_name", "vehicle", "service", "preferred_date", "preferred_window", "status", "created_at")
    list_filter = ("status", "preferred_window", "visit_type", "preferred_date")
    search_fields = ("reference", "full_name", "phone_number", "email", "vehicle", "service")
    readonly_fields = ("reference", "created_at", "updated_at", "ip_address", "user_agent")
    date_hierarchy = "preferred_date"


class PhotoRequestImageInline(admin.TabularInline):
    model = PhotoRequestImage
    extra = 0
    readonly_fields = ("uploaded_at",)


@admin.register(PhotoRequest)
class PhotoRequestAdmin(admin.ModelAdmin):
    list_display = ("reference", "full_name", "vehicle", "damage_type", "status", "retention_expires_at", "created_at")
    list_filter = ("status", "damage_type", "created_at", "retention_expires_at")
    search_fields = ("reference", "full_name", "phone_number", "email", "vehicle", "description")
    readonly_fields = ("reference", "created_at", "updated_at", "ip_address", "user_agent", "retention_expires_at")
    inlines = [PhotoRequestImageInline]
    date_hierarchy = "created_at"


@admin.register(RepairStory)
class RepairStoryAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "vehicle", "customer_permission", "is_published", "display_order")
    list_filter = ("category", "customer_permission", "is_published")
    search_fields = ("title", "vehicle", "summary", "work_done")
    prepopulated_fields = {"slug": ("title",)}
    fieldsets = (
        (None, {"fields": ("title", "slug", "category", "vehicle", "completed_on", "display_order")}),
        ("Story", {"fields": ("summary", "work_done")}),
        ("Photos", {"fields": ("before_image", "after_image")}),
        ("Publishing", {"fields": ("customer_permission", "is_published")}),
    )


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("author", "rating", "category_label", "source_label", "is_published", "display_order")
    list_filter = ("rating", "category", "is_published", "source_label")
    search_fields = ("author", "quote")
    list_editable = ("is_published", "display_order")


@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "phone", "updated_at")
    list_filter = ("role",)
    search_fields = ("user__username", "user__first_name", "user__last_name", "phone")
    autocomplete_fields = ("user",)


@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "phone", "updated_at")
    search_fields = ("user__username", "user__first_name", "user__last_name", "user__email", "phone")
    autocomplete_fields = ("user",)


@admin.register(WorkTicket)
class WorkTicketAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "work_type",
        "vehicle",
        "assignee",
        "status",
        "due_date",
        "created_at",
    )
    list_filter = ("status", "assignee", "due_date", "created_at")
    search_fields = (
        "reference",
        "work_type",
        "vehicle",
        "customer_name",
        "customer_phone",
        "assignee__username",
        "booking__reference",
    )
    readonly_fields = ("reference", "created_at", "updated_at")
    autocomplete_fields = ("assignee", "booking", "created_by")
    date_hierarchy = "created_at"


class EstimateAddOnInline(admin.TabularInline):
    model = EstimateAddOn
    extra = 0
    fields = ("label", "amount", "enabled", "display_order")


@admin.register(EstimateService)
class EstimateServiceAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "slug",
        "enabled",
        "base_price",
        "spread_percent",
        "unit_label",
        "uses_severity",
        "display_order",
        "updated_at",
    )
    list_filter = ("enabled", "uses_severity")
    search_fields = ("slug", "unit_label", "notes")
    readonly_fields = ("created_at", "updated_at", "updated_by")
    inlines = [EstimateAddOnInline]
    fieldsets = (
        (None, {"fields": ("slug", "enabled", "display_order")}),
        ("Pricing", {"fields": ("base_price", "spread_percent", "unit_label", "uses_severity")}),
        ("Notes", {"fields": ("notes", "updated_by", "created_at", "updated_at")}),
    )


@admin.register(EstimateSettings)
class EstimateSettingsAdmin(admin.ModelAdmin):
    list_display = ("site_enabled", "rounding_step", "prices_updated_on", "updated_at")

    def has_add_permission(self, request):
        return not EstimateSettings.objects.exists()


@admin.register(AnalyticsEvent)
class AnalyticsEventAdmin(admin.ModelAdmin):
    list_display = ("name", "path", "created_at")
    list_filter = ("name", "created_at")
    search_fields = ("name", "path", "page_title", "referrer")
    readonly_fields = ("name", "path", "page_title", "referrer", "session_key", "metadata", "created_at")
    date_hierarchy = "created_at"


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("name", "contact_name", "phone", "email", "lead_time_days", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "contact_name", "phone", "email", "account_number")


@admin.register(Part)
class PartAdmin(admin.ModelAdmin):
    list_display = (
        "sku",
        "name",
        "category",
        "bin_location",
        "quantity_on_hand",
        "reorder_level",
        "reorder_target",
        "supplier",
        "is_critical",
        "is_active",
    )
    list_filter = ("is_active", "is_critical", "category", "supplier")
    search_fields = ("sku", "name", "part_number", "barcode", "bin_location", "brand")
    autocomplete_fields = ("supplier",)
    readonly_fields = ("quantity_on_hand", "last_counted_at", "created_at", "updated_at")


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = (
        "part",
        "kind",
        "quantity_delta",
        "balance_after",
        "unit_cost",
        "work_ticket",
        "created_by",
        "created_at",
    )
    list_filter = ("kind", "created_at")
    search_fields = ("part__sku", "part__name", "reason", "work_ticket__reference")
    readonly_fields = (
        "part",
        "kind",
        "quantity_delta",
        "balance_after",
        "unit_cost",
        "work_ticket",
        "created_by",
        "reason",
        "created_at",
    )
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
