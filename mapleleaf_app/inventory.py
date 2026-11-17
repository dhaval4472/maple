"""Stockroom rules and the append-only movement service.

Only this module writes ``Part.quantity_on_hand``. Views, forms and the admin
all go through :func:`record_movement`, so every quantity change has a matching
ledger row with a balance snapshot and an author.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from .models import Part, StockMovement

ZERO = Decimal("0.00")


def _as_decimal(value):
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError("Enter a valid cost, for example 12.50.")


def record_movement(
    part,
    kind,
    quantity,
    *,
    user=None,
    ticket=None,
    reason="",
    unit_cost=None,
):
    """Create one stock movement and update the cached balance atomically.

    ``quantity`` means:

    * ``receive`` / ``use`` / ``return`` — a positive magnitude
    * ``count`` — the new counted quantity (may be zero)
    * ``adjust`` — a signed change, for example ``-2`` or ``3``
    """

    valid_kinds = {value for value, _label in StockMovement.KIND_CHOICES}
    if kind not in valid_kinds:
        raise ValidationError("That stock action was not understood.")

    try:
        quantity = int(quantity)
    except (TypeError, ValueError):
        raise ValidationError("Enter a whole number.")

    unit_cost = _as_decimal(unit_cost)
    reason = (reason or "").strip()

    with transaction.atomic():
        locked = Part.objects.select_for_update().get(pk=part.pk)

        if kind == StockMovement.KIND_RECEIVE:
            delta = abs(quantity)
        elif kind == StockMovement.KIND_USE:
            delta = -abs(quantity)
        elif kind == StockMovement.KIND_RETURN:
            delta = abs(quantity)
        elif kind == StockMovement.KIND_COUNT:
            if quantity < 0:
                raise ValidationError("A counted quantity cannot be negative.")
            delta = quantity - locked.quantity_on_hand
        else:  # adjust
            delta = quantity

        if delta == 0:
            raise ValidationError("That would not change the stock level.")
        if kind in (StockMovement.KIND_USE, StockMovement.KIND_RETURN) and quantity <= 0:
            raise ValidationError("Enter a quantity of at least 1.")
        if kind == StockMovement.KIND_RECEIVE and quantity <= 0:
            raise ValidationError("Enter a quantity of at least 1.")

        new_balance = locked.quantity_on_hand + delta
        if new_balance < 0:
            raise ValidationError(
                f"Only {locked.quantity_on_hand} {locked.get_unit_display().lower()} "
                f"of {locked.name} are on the shelf. Receive stock or record a count first."
            )

        movement = StockMovement.objects.create(
            part=locked,
            kind=kind,
            quantity_delta=delta,
            balance_after=new_balance,
            unit_cost=unit_cost if unit_cost is not None else locked.cost_price,
            work_ticket=ticket,
            created_by=user if getattr(user, "is_authenticated", False) else None,
            reason=reason,
        )

        locked.quantity_on_hand = new_balance
        update_fields = ["quantity_on_hand", "updated_at"]

        if kind == StockMovement.KIND_RECEIVE and unit_cost is not None:
            locked.cost_price = unit_cost
            update_fields.append("cost_price")
        if kind == StockMovement.KIND_COUNT:
            locked.last_counted_at = timezone.now()
            update_fields.append("last_counted_at")

        locked.save(update_fields=update_fields)

    part.refresh_from_db()
    return movement


def low_stock_parts():
    """Active, tracked parts at or below their reorder level."""

    return (
        Part.objects.filter(
            is_active=True,
            reorder_level__gt=0,
            quantity_on_hand__lte=F("reorder_level"),
        )
        .select_related("supplier")
        .order_by("-is_critical", "quantity_on_hand", "name")
    )


def low_stock_count():
    return low_stock_parts().count()


def reorder_groups(parts=None):
    """Group low-stock parts by supplier for the shopping list."""

    parts = list(parts if parts is not None else low_stock_parts())
    groups = {}
    for part in parts:
        key = part.supplier_id or 0
        group = groups.setdefault(
            key,
            {
                "supplier": part.supplier,
                "parts": [],
                "suggested_quantity": 0,
                "estimated_cost": ZERO,
            },
        )
        group["parts"].append(part)
        group["suggested_quantity"] += part.suggested_order_quantity
        group["estimated_cost"] += part.suggested_order_quantity * (part.cost_price or ZERO)

    ordered = sorted(
        groups.values(),
        key=lambda group: (
            group["supplier"] is None,
            (group["supplier"].name if group["supplier"] else "").lower(),
        ),
    )
    return ordered


def ticket_part_rows(ticket):
    """Net parts used on a ticket, grouped by part."""

    rows = {}
    movements = (
        ticket.part_movements.select_related("part")
        .order_by("created_at", "id")
    )
    for movement in movements:
        row = rows.setdefault(
            movement.part_id,
            {
                "part": movement.part,
                "quantity": 0,
                "cost": ZERO,
                "last_movement": movement,
            },
        )
        row["quantity"] -= movement.quantity_delta
        if movement.unit_cost is not None:
            row["cost"] -= movement.quantity_delta * movement.unit_cost
        row["last_movement"] = movement

    return [row for row in rows.values() if row["quantity"] != 0]


def ticket_parts_total(ticket):
    return sum((row["cost"] for row in ticket_part_rows(ticket)), ZERO)


def usage_since(since):
    """Units taken from stock since a timestamp."""

    result = StockMovement.objects.filter(
        kind=StockMovement.KIND_USE,
        created_at__gte=since,
    ).aggregate(total=Sum("quantity_delta"))["total"]
    return abs(result or 0)


def rebuild_stock_balances(dry_run=False):
    """Recalculate every cached balance from the ledger.

    Returns a list of ``(part, old_balance, new_balance)`` changes. Movement
    ``balance_after`` snapshots are repaired at the same time when they drift.
    """

    changes = []
    for part in Part.objects.all().order_by("pk"):
        balance = 0
        movement_updates = []
        for movement in part.movements.order_by("created_at", "id"):
            balance += movement.quantity_delta
            if movement.balance_after != balance:
                movement.balance_after = balance
                movement_updates.append(movement)

        if part.quantity_on_hand != balance:
            changes.append((part, part.quantity_on_hand, balance))

        if not dry_run:
            if movement_updates:
                StockMovement.objects.bulk_update(movement_updates, ["balance_after"])
            if part.quantity_on_hand != balance:
                part.quantity_on_hand = balance
                part.save(update_fields=["quantity_on_hand", "updated_at"])

    return changes
