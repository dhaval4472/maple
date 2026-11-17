"""Pure pricing helpers for the public repair estimator.

Every number comes from the rows the shop owner edits in the staff Estimator
section. Nothing here invents a price, applies a market average or guesses at
parts availability. The result is a planning range, not a quote.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR

VEHICLE_CLASSES = [
    ("car", "Car or small SUV"),
    ("suv", "SUV, van or pickup"),
    ("luxury", "Luxury or premium"),
]

SEVERITY_CHOICES = [
    ("minor", "Minor"),
    ("moderate", "Moderate"),
    ("severe", "Severe"),
]

CLAIM_CHOICES = [
    ("private", "Private work — I am paying"),
    ("mpi", "Insurance or MPI claim"),
]

VEHICLE_MULTIPLIER_FIELDS = {
    "car": "car_multiplier",
    "suv": "suv_multiplier",
    "luxury": "luxury_multiplier",
}

SEVERITY_MULTIPLIER_FIELDS = {
    "minor": "severity_minor",
    "moderate": "severity_moderate",
    "severe": "severity_severe",
}

ZERO = Decimal("0")


def money(value):
    """Format a Decimal as a whole-dollar CAD amount."""
    if value is None:
        return "—"
    amount = Decimal(value)
    if amount == amount.to_integral_value():
        return f"${amount:,.0f}"
    return f"${amount:,.2f}"


def _round_down(value, step):
    step = Decimal(step)
    if step <= 0:
        return value
    return (value / step).to_integral_value(rounding=ROUND_FLOOR) * step


def _round_up(value, step):
    step = Decimal(step)
    if step <= 0:
        return value
    return (value / step).to_integral_value(rounding=ROUND_CEILING) * step


@dataclass(frozen=True)
class EstimateFactor:
    label: str
    detail: str


@dataclass(frozen=True)
class EstimateAddOnLine:
    label: str
    amount: Decimal

    @property
    def amount_display(self):
        return money(self.amount)


@dataclass(frozen=True)
class EstimateResult:
    service_title: str
    low: Decimal
    high: Decimal
    unit_label: str
    factors: list[EstimateFactor] = field(default_factory=list)
    addons: list[EstimateAddOnLine] = field(default_factory=list)
    disclaimer: str = ""
    updated_on: object = None

    @property
    def low_display(self):
        return money(self.low)

    @property
    def high_display(self):
        return money(self.high)

    @property
    def range_display(self):
        return f"{self.low_display} – {self.high_display}"

    @property
    def callback_note(self):
        lines = [
            f"Planning estimate: {self.service_title}",
            f"Range: {self.range_display} CAD {self.unit_label}",
        ]
        for factor in self.factors:
            lines.append(f"- {factor.label}: {factor.detail}")
        for addon in self.addons:
            lines.append(f"- {addon.label}: +{addon.amount_display}")
        lines.append("Not a quote. Please confirm after inspection.")
        return "\n".join(lines)


def _multiplier(settings_obj, field_name):
    value = getattr(settings_obj, field_name, None)
    if value is None or value <= 0:
        return Decimal("1")
    return Decimal(value)


def price_estimate(
    service,
    *,
    vehicle_class="car",
    severity="moderate",
    addons=(),
    settings_obj=None,
):
    """Return an :class:`EstimateResult`, or ``None`` when no price is published.

    ``None`` is the honest answer when the site switch is off, the service is
    disabled, or the master has not entered a base price yet.
    """
    if settings_obj is None:
        from .models import EstimateSettings

        settings_obj = EstimateSettings.load()

    if not settings_obj.site_enabled:
        return None
    if not service.enabled or service.base_price is None or service.base_price <= 0:
        return None

    base = Decimal(service.base_price)
    spread = Decimal(service.spread_percent or 0) / Decimal("100")
    if spread < 0:
        spread = ZERO

    vehicle_field = VEHICLE_MULTIPLIER_FIELDS.get(vehicle_class, "car_multiplier")
    vehicle_mult = _multiplier(settings_obj, vehicle_field)
    vehicle_label = dict(VEHICLE_CLASSES).get(vehicle_class, "Car or small SUV")

    factors = [
        EstimateFactor("Vehicle", f"{vehicle_label} ×{vehicle_mult:.2f}"),
    ]

    severity_mult = Decimal("1")
    if service.uses_severity:
        severity_field = SEVERITY_MULTIPLIER_FIELDS.get(severity, "severity_moderate")
        severity_mult = _multiplier(settings_obj, severity_field)
        severity_label = dict(SEVERITY_CHOICES).get(severity, "Moderate")
        factors.append(EstimateFactor("Damage", f"{severity_label} ×{severity_mult:.2f}"))

    addon_lines = []
    addon_total = ZERO
    for addon in addons:
        amount = Decimal(addon.amount or 0)
        if amount < 0:
            amount = ZERO
        addon_total += amount
        addon_lines.append(EstimateAddOnLine(addon.label, amount))

    core_low = base * (1 - spread) * vehicle_mult * severity_mult
    core_high = base * (1 + spread) * vehicle_mult * severity_mult

    step = Decimal(settings_obj.rounding_step or 1)
    low = _round_down(core_low + addon_total, step)
    high = _round_up(core_high + addon_total, step)
    if high < low:
        low, high = high, low
    if high == low:
        high = low + step

    return EstimateResult(
        service_title=service.title,
        low=low,
        high=high,
        unit_label=service.unit_label or "per job",
        factors=factors,
        addons=addon_lines,
        disclaimer=settings_obj.disclaimer,
        updated_on=settings_obj.prices_updated_on,
    )


def starting_price(service, *, settings_obj=None):
    """Return the lowest rounded range floor for a service, or ``None``.

    Used for the "From $X" hint on the service cards. It checks every vehicle
    class and severity the form could offer, so the hint can never advertise a
    lower number than the estimator itself would produce.
    """
    if settings_obj is None:
        from .models import EstimateSettings

        settings_obj = EstimateSettings.load()

    vehicles = [value for value, _ in VEHICLE_CLASSES]
    severities = [value for value, _ in SEVERITY_CHOICES] if service.uses_severity else ["minor"]

    floors = []
    for vehicle_class in vehicles:
        for severity in severities:
            result = price_estimate(
                service,
                vehicle_class=vehicle_class,
                severity=severity,
                settings_obj=settings_obj,
            )
            if result is not None:
                floors.append(result.low)
    return min(floors) if floors else None
