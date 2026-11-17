from datetime import timedelta
import json

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from mapleleaf_app import inventory
from mapleleaf_app.models import (
    BookingRequest,
    CallbackRequest,
    CustomerProfile,
    Part,
    StaffProfile,
    StockMovement,
    Supplier,
    WorkTicket,
)


class WorkTicketTestBase(TestCase):
    def setUp(self):
        cache.clear()
        User = get_user_model()
        self.master = User.objects.create_user(
            username="owner",
            password="owner-pass-123",
            first_name="Shop",
            last_name="Owner",
            is_staff=True,
        )
        StaffProfile.objects.create(user=self.master, role=StaffProfile.ROLE_MASTER)

        self.employee = User.objects.create_user(
            username="jordan",
            password="employee-pass-123",
            first_name="Jordan",
            last_name="Lee",
            is_staff=False,
        )
        StaffProfile.objects.create(
            user=self.employee,
            role=StaffProfile.ROLE_EMPLOYEE,
            phone="204-555-0101",
        )

        self.other = User.objects.create_user(
            username="sam",
            password="employee-pass-456",
            first_name="Sam",
            last_name="Park",
            is_staff=False,
        )
        StaffProfile.objects.create(user=self.other, role=StaffProfile.ROLE_EMPLOYEE)

    def make_ticket(self, assignee=None, **overrides):
        values = {
            "work_type": "Paint driver-side door",
            "vehicle": "2019 Honda Civic, silver",
            "assignee": assignee or self.employee,
            "customer_name": "Avery Chen",
            "customer_phone": "204-555-0199",
            "created_by": self.master,
        }
        values.update(overrides)
        return WorkTicket.objects.create(**values)


class RoleAccessTests(WorkTicketTestBase):
    def test_master_login_lands_on_dashboard(self):
        response = self.client.post(
            reverse("staff_login"),
            {"username": "owner", "password": "owner-pass-123"},
        )
        self.assertRedirects(response, reverse("staff_dashboard"), fetch_redirect_response=False)

    def test_employee_login_lands_on_my_work(self):
        response = self.client.post(
            reverse("staff_login"),
            {"username": "jordan", "password": "employee-pass-123"},
        )
        self.assertRedirects(response, reverse("staff_my_work"), fetch_redirect_response=False)

    def test_non_workspace_user_cannot_sign_in(self):
        get_user_model().objects.create_user(
            username="outside",
            password="outside-pass-123",
        )
        response = self.client.post(
            reverse("staff_login"),
            {"username": "outside", "password": "outside-pass-123"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "does not have workspace access")

    def test_unified_login_sends_master_to_dashboard(self):
        response = self.client.post(
            reverse("login"),
            {"username": "owner", "password": "owner-pass-123"},
        )
        self.assertRedirects(
            response, reverse("staff_dashboard"), fetch_redirect_response=False
        )

    def test_unified_login_sends_employee_to_my_work(self):
        response = self.client.post(
            reverse("login"),
            {"username": "jordan", "password": "employee-pass-123"},
        )
        self.assertRedirects(
            response, reverse("staff_my_work"), fetch_redirect_response=False
        )

    def test_unified_login_rejects_account_without_an_area(self):
        get_user_model().objects.create_user(
            username="outside",
            password="outside-pass-123",
        )
        response = self.client.post(
            reverse("login"),
            {"username": "outside", "password": "outside-pass-123"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "does not have access to a sign-in area")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_unified_login_throttles_repeated_failures(self):
        for _ in range(8):
            self.client.post(
                reverse("login"),
                {"username": "owner", "password": "wrong-password"},
            )
        response = self.client.post(
            reverse("login"),
            {"username": "owner", "password": "owner-pass-123"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Too many sign-in attempts")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_signed_in_workspace_user_skips_login_page(self):
        pages = (
            (self.master, "staff_dashboard"),
            (self.employee, "staff_my_work"),
        )
        for user, destination in pages:
            with self.subTest(destination=destination):
                self.client.force_login(user)
                response = self.client.get(reverse("login"))
                self.assertRedirects(
                    response,
                    reverse(destination),
                    fetch_redirect_response=False,
                )

    def test_public_nav_shows_one_login_link_beside_contact(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, f'href="{reverse("login")}"')
        self.assertContains(response, ">Login<")

        self.client.force_login(self.master)
        response = self.client.get(reverse("home"))
        self.assertContains(response, f'href="{reverse("staff_dashboard")}"')
        self.assertContains(response, ">Dashboard<")
        self.assertNotContains(response, f'href="{reverse("login")}"')

    def test_employee_cannot_open_master_pages(self):
        self.client.force_login(self.employee)
        for name in ("staff_dashboard", "staff_work", "staff_team", "staff_reviews", "staff_analytics"):
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertRedirects(
                    response,
                    reverse("staff_my_work"),
                    fetch_redirect_response=False,
                )

    def test_master_cannot_open_employee_workspace(self):
        self.client.force_login(self.master)
        response = self.client.get(reverse("staff_my_work"))
        self.assertRedirects(
            response,
            reverse("staff_dashboard"),
            fetch_redirect_response=False,
        )

    def test_employee_can_open_own_account(self):
        self.client.force_login(self.employee)
        response = self.client.get(reverse("staff_account"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Employee")

    def test_employee_can_update_own_phone(self):
        self.client.force_login(self.employee)
        response = self.client.post(
            reverse("staff_account"),
            {
                "first_name": "Jordan",
                "last_name": "Lee",
                "email": "jordan@example.com",
                "phone": "204-555-0777",
            },
        )
        self.assertRedirects(
            response,
            reverse("staff_account"),
            fetch_redirect_response=False,
        )
        self.employee.refresh_from_db()
        self.employee.staff_profile.refresh_from_db()
        self.assertEqual(self.employee.staff_profile.phone, "204-555-0777")
        self.assertEqual(self.employee.staff_profile.role, StaffProfile.ROLE_EMPLOYEE)

    def test_master_profile_keeps_master_role(self):
        self.client.force_login(self.master)
        self.client.post(
            reverse("staff_account"),
            {
                "first_name": "Shop",
                "last_name": "Owner",
                "email": "owner@example.com",
                "phone": "",
            },
        )
        self.master.staff_profile.refresh_from_db()
        self.assertEqual(self.master.staff_profile.role, StaffProfile.ROLE_MASTER)


class WorkTicketAccessTests(WorkTicketTestBase):
    def test_employee_sees_only_own_tickets(self):
        mine = self.make_ticket(work_type="Paint the hood")
        theirs = self.make_ticket(assignee=self.other, work_type="Replace windshield")

        self.client.force_login(self.employee)
        response = self.client.get(reverse("staff_my_work"))
        self.assertContains(response, mine.reference)
        self.assertNotContains(response, theirs.reference)

    def test_employee_cannot_open_another_ticket(self):
        theirs = self.make_ticket(assignee=self.other)
        self.client.force_login(self.employee)
        response = self.client.get(reverse("staff_my_work_detail", args=[theirs.pk]))
        self.assertEqual(response.status_code, 404)

    def test_employee_cannot_post_to_another_ticket(self):
        theirs = self.make_ticket(assignee=self.other)
        self.client.force_login(self.employee)
        response = self.client.post(
            reverse("staff_my_work_detail", args=[theirs.pk]),
            {"action": "start"},
        )
        self.assertEqual(response.status_code, 404)
        theirs.refresh_from_db()
        self.assertEqual(theirs.status, WorkTicket.STATUS_ASSIGNED)


class WorkTicketFlowTests(WorkTicketTestBase):
    def test_ticket_reference_uses_wt_prefix(self):
        ticket = self.make_ticket()
        self.assertTrue(ticket.reference.startswith("WT-"))

    def test_employee_starts_and_completes_ticket(self):
        ticket = self.make_ticket()
        self.client.force_login(self.employee)

        response = self.client.post(
            reverse("staff_my_work_detail", args=[ticket.pk]),
            {"action": "start"},
        )
        self.assertRedirects(
            response,
            reverse("staff_my_work_detail", args=[ticket.pk]),
            fetch_redirect_response=False,
        )
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, WorkTicket.STATUS_IN_PROGRESS)
        self.assertIsNotNone(ticket.started_at)
        self.assertIsNone(ticket.completed_at)

        self.client.post(
            reverse("staff_my_work_detail", args=[ticket.pk]),
            {"action": "complete"},
        )
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, WorkTicket.STATUS_COMPLETED)
        self.assertIsNotNone(ticket.completed_at)

    def test_cannot_complete_before_starting(self):
        ticket = self.make_ticket()
        self.client.force_login(self.employee)
        self.client.post(
            reverse("staff_my_work_detail", args=[ticket.pk]),
            {"action": "complete"},
        )
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, WorkTicket.STATUS_ASSIGNED)
        self.assertIsNone(ticket.completed_at)

    def test_employee_can_save_work_notes(self):
        ticket = self.make_ticket()
        self.client.force_login(self.employee)
        response = self.client.post(
            reverse("staff_my_work_detail", args=[ticket.pk]),
            {"action": "save_note", "employee_notes": "Primer is drying overnight."},
        )
        self.assertRedirects(
            response,
            reverse("staff_my_work_detail", args=[ticket.pk]),
            fetch_redirect_response=False,
        )
        ticket.refresh_from_db()
        self.assertEqual(ticket.employee_notes, "Primer is drying overnight.")

    def test_master_can_create_ticket(self):
        self.client.force_login(self.master)
        response = self.client.post(
            reverse("staff_work_create"),
            {
                "work_type": "Brake inspection",
                "vehicle": "2021 Toyota RAV4, white",
                "assignee": self.employee.pk,
                "customer_name": "Morgan Reid",
                "customer_phone": "204-555-0111",
                "due_date": (timezone.localdate() + timedelta(days=2)).isoformat(),
                "instructions": "Check front pads and rotors.",
            },
        )
        ticket = WorkTicket.objects.get()
        self.assertRedirects(
            response,
            reverse("staff_work_detail", args=[ticket.pk]),
            fetch_redirect_response=False,
        )
        self.assertEqual(ticket.work_type, "Brake inspection")
        self.assertEqual(ticket.assignee, self.employee)
        self.assertEqual(ticket.created_by, self.master)
        self.assertEqual(ticket.status, WorkTicket.STATUS_ASSIGNED)

    def test_master_must_choose_employee(self):
        self.client.force_login(self.master)
        response = self.client.post(
            reverse("staff_work_create"),
            {
                "work_type": "Brake inspection",
                "vehicle": "2021 Toyota RAV4, white",
                "assignee": self.master.pk,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(WorkTicket.objects.count(), 0)
        self.assertContains(response, "Select a valid choice")

    def test_reassigning_active_ticket_resets_state(self):
        ticket = self.make_ticket(
            status=WorkTicket.STATUS_IN_PROGRESS,
            started_at=timezone.now(),
        )
        self.client.force_login(self.master)
        response = self.client.post(
            reverse("staff_work_edit", args=[ticket.pk]),
            {
                "work_type": ticket.work_type,
                "vehicle": ticket.vehicle,
                "assignee": self.other.pk,
                "customer_name": ticket.customer_name,
                "customer_phone": ticket.customer_phone,
                "due_date": "",
                "instructions": ticket.instructions,
            },
        )
        self.assertRedirects(
            response,
            reverse("staff_work_detail", args=[ticket.pk]),
            fetch_redirect_response=False,
        )
        ticket.refresh_from_db()
        self.assertEqual(ticket.assignee, self.other)
        self.assertEqual(ticket.status, WorkTicket.STATUS_ASSIGNED)
        self.assertIsNone(ticket.started_at)
        self.assertIsNone(ticket.completed_at)

    def test_completed_ticket_must_be_reopened_before_editing(self):
        ticket = self.make_ticket(
            status=WorkTicket.STATUS_COMPLETED,
            completed_at=timezone.now(),
        )
        self.client.force_login(self.master)
        response = self.client.get(reverse("staff_work_edit", args=[ticket.pk]))
        self.assertRedirects(
            response,
            reverse("staff_work_detail", args=[ticket.pk]),
            fetch_redirect_response=False,
        )

    def test_master_can_cancel_and_reopen(self):
        ticket = self.make_ticket()
        self.client.force_login(self.master)

        self.client.post(reverse("staff_work_cancel", args=[ticket.pk]))
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, WorkTicket.STATUS_CANCELLED)

        self.client.post(reverse("staff_work_reopen", args=[ticket.pk]))
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, WorkTicket.STATUS_ASSIGNED)
        self.assertIsNone(ticket.started_at)
        self.assertIsNone(ticket.completed_at)

    def test_booking_prefills_new_ticket(self):
        booking = BookingRequest.objects.create(
            full_name="Avery Chen",
            phone_number="204-555-0199",
            vehicle="2020 Mazda CX-5, blue",
            service="Dent repair & painting",
            preferred_date=timezone.localdate() + timedelta(days=3),
            preferred_window="9:00–11:00 AM",
            notes="Small dent on the rear door.",
        )
        self.client.force_login(self.master)
        response = self.client.get(
            reverse("staff_work_create") + f"?booking={booking.pk}"
        )
        self.assertEqual(response.status_code, 200)
        initial = response.context["form"].initial
        self.assertEqual(initial["vehicle"], booking.vehicle)
        self.assertEqual(initial["work_type"], booking.service)
        self.assertEqual(initial["customer_name"], booking.full_name)
        self.assertEqual(initial["customer_phone"], booking.phone_number)
        self.assertEqual(response.context["booking"], booking)

    def test_booking_prefill_saves_link(self):
        booking = BookingRequest.objects.create(
            full_name="Avery Chen",
            phone_number="204-555-0199",
            vehicle="2020 Mazda CX-5, blue",
            service="Dent repair & painting",
            preferred_date=timezone.localdate() + timedelta(days=3),
            preferred_window="9:00–11:00 AM",
        )
        self.client.force_login(self.master)
        response = self.client.post(
            reverse("staff_work_create"),
            {
                "booking": booking.pk,
                "work_type": "Dent repair & painting",
                "vehicle": booking.vehicle,
                "assignee": self.employee.pk,
                "customer_name": booking.full_name,
                "customer_phone": booking.phone_number,
                "due_date": "",
                "instructions": "",
            },
        )
        ticket = WorkTicket.objects.get()
        self.assertRedirects(
            response,
            reverse("staff_work_detail", args=[ticket.pk]),
            fetch_redirect_response=False,
        )
        self.assertEqual(ticket.booking, booking)


class TeamTests(WorkTicketTestBase):
    def test_master_can_create_employee_account(self):
        self.client.force_login(self.master)
        response = self.client.post(
            reverse("staff_team_create"),
            {
                "username": "casey",
                "first_name": "Casey",
                "last_name": "Ng",
                "email": "casey@example.com",
                "phone": "204-555-0122",
                "password1": "A-strong-temp-pass-123",
                "password2": "A-strong-temp-pass-123",
            },
        )
        self.assertRedirects(response, reverse("staff_team"), fetch_redirect_response=False)
        employee = get_user_model().objects.get(username="casey")
        self.assertFalse(employee.is_staff)
        self.assertFalse(employee.is_superuser)
        self.assertEqual(employee.staff_profile.role, StaffProfile.ROLE_EMPLOYEE)
        self.assertEqual(employee.staff_profile.phone, "204-555-0122")

    def test_deactivation_blocked_while_ticket_open(self):
        ticket = self.make_ticket()
        self.client.force_login(self.master)
        response = self.client.post(
            reverse("staff_team_toggle", args=[self.employee.pk])
        )
        self.assertRedirects(response, reverse("staff_team"), fetch_redirect_response=False)
        self.employee.refresh_from_db()
        self.assertTrue(self.employee.is_active)

        ticket.status = WorkTicket.STATUS_COMPLETED
        ticket.completed_at = timezone.now()
        ticket.save(update_fields=["status", "completed_at"])

        self.client.post(reverse("staff_team_toggle", args=[self.employee.pk]))
        self.employee.refresh_from_db()
        self.assertFalse(self.employee.is_active)

    def test_deactivated_employee_cannot_sign_in(self):
        self.employee.is_active = False
        self.employee.save(update_fields=["is_active"])
        response = self.client.post(
            reverse("staff_login"),
            {"username": "jordan", "password": "employee-pass-123"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "did not match")

    def test_employee_cannot_manage_team(self):
        self.client.force_login(self.employee)
        response = self.client.get(reverse("staff_team"))
        self.assertRedirects(
            response,
            reverse("staff_my_work"),
            fetch_redirect_response=False,
        )


class InventoryTestBase(WorkTicketTestBase):
    def make_part(self, **overrides):
        suffix = Part.objects.count() + 1
        values = {
            "sku": f"BP-{suffix:04d}",
            "name": f"Panel Bond {suffix}",
            "category": Part.CATEGORY_PAINT,
            "unit": Part.UNIT_EACH,
            "bin_location": "A-01-1",
            "cost_price": "12.34",
            "reorder_level": 2,
            "reorder_target": 6,
        }
        values.update(overrides)
        return Part.objects.create(**values)

    def stock_up(self, part, quantity=5, user=None):
        inventory.record_movement(
            part,
            StockMovement.KIND_RECEIVE,
            quantity,
            user=user or self.master,
        )
        part.refresh_from_db()
        return part


class InventoryPermissionTests(InventoryTestBase):
    def test_master_can_add_part(self):
        self.client.force_login(self.master)
        response = self.client.post(
            reverse("staff_part_create"),
            {
                "sku": "new-1",
                "name": "New fender",
                "category": Part.CATEGORY_BODY,
                "brand": "OEM",
                "part_number": "fnd-22",
                "barcode": "",
                "bin_location": "b-2-1",
                "unit": Part.UNIT_EACH,
                "supplier": "",
                "cost_price": "5.00",
                "reorder_level": "1",
                "reorder_target": "4",
                "is_critical": "on",
                "is_active": "on",
                "notes": "",
            },
        )
        part = Part.objects.get()
        self.assertRedirects(
            response,
            reverse("staff_part_detail", args=[part.pk]),
            fetch_redirect_response=False,
        )
        self.assertEqual(part.sku, "NEW-1")
        self.assertEqual(part.bin_location, "B-2-1")
        self.assertEqual(part.part_number, "FND-22")
        self.assertEqual(part.quantity_on_hand, 0)
        self.assertTrue(part.is_critical)

    def test_employee_can_search_parts_without_costs(self):
        part = self.make_part(name="Panel Bond", cost_price="12.34")
        self.stock_up(part, 5)

        self.client.force_login(self.employee)
        response = self.client.get(reverse("staff_parts"), {"q": "Panel"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Panel Bond")
        self.assertContains(response, "On hand")
        self.assertNotContains(response, "12.34")
        self.assertNotContains(response, "Unit cost")
        self.assertNotContains(response, "Stock value")

        detail = self.client.get(reverse("staff_part_detail", args=[part.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "Panel Bond")
        self.assertContains(detail, "Use stock")
        self.assertNotContains(detail, "12.34")
        self.assertNotContains(detail, "Unit cost")
        self.assertNotContains(detail, "Stock value")

    def test_employee_cannot_open_inventory_admin(self):
        part = self.make_part()
        self.client.force_login(self.employee)
        pages = [
            reverse("staff_part_create"),
            reverse("staff_part_receive", args=[part.pk]),
            reverse("staff_part_count", args=[part.pk]),
            reverse("staff_part_adjust", args=[part.pk]),
            reverse("staff_bulk_receive"),
            reverse("staff_reorder"),
            reverse("staff_reorder_export"),
            reverse("staff_suppliers"),
            reverse("staff_inventory_export"),
            reverse("staff_inventory_template"),
            reverse("staff_inventory_import"),
        ]
        for url in pages:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertRedirects(
                    response,
                    reverse("staff_my_work"),
                    fetch_redirect_response=False,
                )

    def test_employee_cannot_see_other_employees_movements(self):
        part = self.make_part(name="Panel Bond")
        self.stock_up(part, 5)
        inventory.record_movement(
            part,
            StockMovement.KIND_USE,
            1,
            user=self.other,
            reason="Sam used this on another job",
        )

        self.client.force_login(self.employee)
        response = self.client.get(reverse("staff_part_detail", args=[part.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Sam used this on another job")
        self.assertNotContains(response, "Sam Park")

    def test_employee_cannot_see_archived_part(self):
        part = self.make_part()
        self.client.force_login(self.master)
        self.client.post(reverse("staff_part_toggle", args=[part.pk]))
        part.refresh_from_db()
        self.assertFalse(part.is_active)

        self.client.force_login(self.employee)
        response = self.client.get(reverse("staff_part_detail", args=[part.pk]))
        self.assertEqual(response.status_code, 404)
        listing = self.client.get(reverse("staff_parts"))
        self.assertNotContains(listing, part.name)


class StockMovementTests(InventoryTestBase):
    def test_receive_raises_balance_and_updates_cost(self):
        part = self.make_part(cost_price="10.00")
        movement = inventory.record_movement(
            part,
            StockMovement.KIND_RECEIVE,
            4,
            user=self.master,
            unit_cost="11.50",
            reason="Invoice 1042",
        )
        part.refresh_from_db()
        self.assertEqual(part.quantity_on_hand, 4)
        self.assertEqual(str(part.cost_price), "11.50")
        self.assertEqual(movement.quantity_delta, 4)
        self.assertEqual(movement.balance_after, 4)
        self.assertEqual(movement.created_by, self.master)

    def test_use_cannot_go_below_zero(self):
        part = self.make_part()
        self.stock_up(part, 2)
        with self.assertRaises(ValidationError):
            inventory.record_movement(
                part,
                StockMovement.KIND_USE,
                3,
                user=self.employee,
            )
        part.refresh_from_db()
        self.assertEqual(part.quantity_on_hand, 2)
        self.assertEqual(
            part.movements.filter(kind=StockMovement.KIND_USE).count(),
            0,
        )

    def test_count_records_real_quantity_and_last_counted(self):
        part = self.make_part()
        self.stock_up(part, 5)
        movement = inventory.record_movement(
            part,
            StockMovement.KIND_COUNT,
            3,
            user=self.master,
            reason="Cycle count",
        )
        part.refresh_from_db()
        self.assertEqual(part.quantity_on_hand, 3)
        self.assertEqual(movement.quantity_delta, -2)
        self.assertEqual(movement.balance_after, 3)
        self.assertIsNotNone(part.last_counted_at)

    def test_zero_change_is_rejected(self):
        part = self.make_part()
        self.stock_up(part, 5)
        with self.assertRaises(ValidationError):
            inventory.record_movement(
                part,
                StockMovement.KIND_COUNT,
                5,
                user=self.master,
            )

    def test_adjustment_can_reduce_stock_with_reason(self):
        part = self.make_part()
        self.stock_up(part, 5)
        movement = inventory.record_movement(
            part,
            StockMovement.KIND_ADJUST,
            -2,
            user=self.master,
            reason="Damaged in handling",
        )
        part.refresh_from_db()
        self.assertEqual(part.quantity_on_hand, 3)
        self.assertEqual(movement.quantity_delta, -2)
        self.assertEqual(movement.reason, "Damaged in handling")

    def test_rebuild_repairs_cached_balance(self):
        part = self.make_part()
        self.stock_up(part, 3)
        Part.objects.filter(pk=part.pk).update(quantity_on_hand=99)

        changes = inventory.rebuild_stock_balances()
        part.refresh_from_db()
        self.assertEqual(part.quantity_on_hand, 3)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0][1], 99)
        self.assertEqual(changes[0][2], 3)


class LowStockTests(InventoryTestBase):
    def test_low_stock_includes_only_active_tracked_parts(self):
        low = self.make_part(name="Low part", reorder_level=2, reorder_target=6)
        self.stock_up(low, 2)
        healthy = self.make_part(name="Healthy part", reorder_level=1, reorder_target=5)
        self.stock_up(healthy, 4)
        untracked = self.make_part(name="Untracked part", reorder_level=0, reorder_target=0)
        archived = self.make_part(
            name="Archived part",
            reorder_level=2,
            reorder_target=5,
            is_active=False,
        )

        parts = list(inventory.low_stock_parts())
        self.assertIn(low, parts)
        self.assertNotIn(healthy, parts)
        self.assertNotIn(untracked, parts)
        self.assertNotIn(archived, parts)
        self.assertEqual(inventory.low_stock_count(), 1)
        self.assertEqual(low.suggested_order_quantity, 4)

    def test_reorder_groups_by_supplier(self):
        supplier = Supplier.objects.create(name="National Autobody")
        part = self.make_part(name="Low part", supplier=supplier)
        self.stock_up(part, 1)
        groups = inventory.reorder_groups()
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["supplier"], supplier)
        self.assertEqual(groups[0]["suggested_quantity"], 5)
        self.assertEqual(groups[0]["estimated_cost"], part.suggested_order_cost)

    def test_reorder_page_and_csv_are_master_only(self):
        part = self.make_part(name="Low part")
        self.stock_up(part, 1)

        self.client.force_login(self.master)
        response = self.client.get(reverse("staff_reorder"))
        self.assertContains(response, part.sku)
        export = self.client.get(reverse("staff_reorder_export"))
        self.assertEqual(export["Content-Type"], "text/csv")
        self.assertIn(part.sku.encode(), export.content)


class TicketPartTests(InventoryTestBase):
    def test_employee_can_use_stock_on_own_open_ticket(self):
        part = self.make_part(name="Panel Bond")
        self.stock_up(part, 5)
        ticket = self.make_ticket()

        self.client.force_login(self.employee)
        response = self.client.post(
            reverse("staff_part_use", args=[part.pk]),
            {"quantity": "2", "ticket": ticket.pk, "note": "Door skin"},
        )
        self.assertRedirects(
            response,
            reverse("staff_my_work_detail", args=[ticket.pk]),
            fetch_redirect_response=False,
        )
        part.refresh_from_db()
        self.assertEqual(part.quantity_on_hand, 3)
        movement = part.movements.get(kind=StockMovement.KIND_USE)
        self.assertEqual(movement.work_ticket, ticket)
        self.assertEqual(movement.created_by, self.employee)
        self.assertEqual(movement.quantity_delta, -2)

    def test_employee_cannot_link_stock_to_another_ticket(self):
        part = self.make_part()
        self.stock_up(part, 5)
        theirs = self.make_ticket(assignee=self.other)

        self.client.force_login(self.employee)
        response = self.client.post(
            reverse("staff_part_use", args=[part.pk]),
            {"quantity": "2", "ticket": theirs.pk, "note": ""},
        )
        self.assertEqual(response.status_code, 200)
        part.refresh_from_db()
        self.assertEqual(part.quantity_on_hand, 5)
        self.assertEqual(part.movements.count(), 1)

    def test_master_ticket_detail_shows_parts_and_total(self):
        part = self.make_part(name="Panel Bond", cost_price="12.34")
        self.stock_up(part, 5)
        ticket = self.make_ticket()
        inventory.record_movement(
            part,
            StockMovement.KIND_USE,
            2,
            user=self.master,
            ticket=ticket,
        )

        self.client.force_login(self.master)
        response = self.client.get(reverse("staff_work_detail", args=[ticket.pk]))
        self.assertContains(response, "Parts used on this job")
        self.assertContains(response, "Panel Bond")
        self.assertContains(response, "24.68")
        self.assertContains(response, "Parts total")

    def test_employee_ticket_detail_hides_costs(self):
        part = self.make_part(name="Panel Bond", cost_price="12.34")
        self.stock_up(part, 5)
        ticket = self.make_ticket()
        inventory.record_movement(
            part,
            StockMovement.KIND_USE,
            2,
            user=self.employee,
            ticket=ticket,
        )

        self.client.force_login(self.employee)
        response = self.client.get(
            reverse("staff_my_work_detail", args=[ticket.pk])
        )
        self.assertContains(response, "Panel Bond")
        self.assertContains(response, "Parts used on this job")
        self.assertNotContains(response, "24.68")
        self.assertNotContains(response, "Parts total")

    def test_master_can_return_part_to_stock(self):
        part = self.make_part()
        self.stock_up(part, 5)
        ticket = self.make_ticket()
        inventory.record_movement(
            part,
            StockMovement.KIND_USE,
            2,
            user=self.employee,
            ticket=ticket,
        )

        self.client.force_login(self.master)
        response = self.client.post(
            reverse("staff_ticket_part_return", args=[ticket.pk]),
            {"part": part.pk, "quantity": "1"},
        )
        self.assertRedirects(
            response,
            reverse("staff_work_detail", args=[ticket.pk]),
            fetch_redirect_response=False,
        )
        part.refresh_from_db()
        self.assertEqual(part.quantity_on_hand, 4)
        rows = inventory.ticket_part_rows(ticket)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["quantity"], 1)


class InventoryFormPageTests(InventoryTestBase):
    def test_receive_page_adds_stock(self):
        part = self.make_part()
        self.client.force_login(self.master)
        response = self.client.post(
            reverse("staff_part_receive", args=[part.pk]),
            {"quantity": "6", "unit_cost": "9.99", "note": "Delivery"},
        )
        self.assertRedirects(
            response,
            reverse("staff_part_detail", args=[part.pk]),
            fetch_redirect_response=False,
        )
        part.refresh_from_db()
        self.assertEqual(part.quantity_on_hand, 6)
        self.assertEqual(str(part.cost_price), "9.99")

    def test_count_page_can_confirm_without_movement(self):
        part = self.make_part()
        self.stock_up(part, 4)
        self.client.force_login(self.master)
        response = self.client.post(
            reverse("staff_part_count", args=[part.pk]),
            {"counted_quantity": "4", "reason": "cycle", "note": ""},
        )
        self.assertRedirects(
            response,
            reverse("staff_part_detail", args=[part.pk]),
            fetch_redirect_response=False,
        )
        part.refresh_from_db()
        self.assertEqual(part.quantity_on_hand, 4)
        self.assertIsNotNone(part.last_counted_at)
        self.assertEqual(
            part.movements.filter(kind=StockMovement.KIND_COUNT).count(),
            0,
        )

    def test_bulk_receive_updates_several_parts(self):
        supplier = Supplier.objects.create(name="National Autobody")
        first = self.make_part(name="First", supplier=supplier)
        second = self.make_part(name="Second", supplier=supplier)

        self.client.force_login(self.master)
        response = self.client.post(
            reverse("staff_bulk_receive"),
            {
                "supplier": supplier.pk,
                f"qty_{first.pk}": "3",
                f"qty_{second.pk}": "2",
            },
        )
        self.assertRedirects(
            response,
            f"{reverse('staff_bulk_receive')}?supplier={supplier.pk}",
            fetch_redirect_response=False,
        )
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.quantity_on_hand, 3)
        self.assertEqual(second.quantity_on_hand, 2)

    def test_master_can_create_supplier(self):
        self.client.force_login(self.master)
        response = self.client.post(
            reverse("staff_supplier_create"),
            {
                "name": "National Autobody Wholesalers",
                "contact_name": "Dana",
                "phone": "204-555-0133",
                "email": "orders@example.com",
                "account_number": "NAW-22",
                "lead_time_days": "3",
                "notes": "Order before noon.",
                "is_active": "on",
            },
        )
        self.assertRedirects(
            response,
            reverse("staff_suppliers"),
            fetch_redirect_response=False,
        )
        supplier = Supplier.objects.get()
        self.assertEqual(supplier.name, "National Autobody Wholesalers")
        self.assertEqual(supplier.lead_time_days, 3)


class InventoryImportTests(InventoryTestBase):
    def upload(self, csv_text, **data):
        upload = SimpleUploadedFile(
            "parts.csv",
            csv_text.encode("utf-8"),
            content_type="text/csv",
        )
        payload = {"csv_file": upload, "create_missing_suppliers": "on"}
        payload.update(data)
        return self.client.post(reverse("staff_inventory_import"), payload)

    def test_import_updates_existing_without_touching_stock(self):
        existing = self.make_part(sku="ABC-1", name="Old name")
        self.stock_up(existing, 5)

        self.client.force_login(self.master)
        csv_text = (
            "sku,name,category,unit,cost_price,opening_stock,reorder_level,reorder_target\n"
            "ABC-1,Updated name,paint,each,10.00,99,1,3\n"
            "NEW-1,Brand new part,body,each,8.00,4,0,0\n"
        )
        preview = self.upload(csv_text)
        self.assertEqual(preview.status_code, 200)
        rows = preview.context["preview_rows"]
        self.assertEqual(len(rows), 2)

        response = self.client.post(
            reverse("staff_inventory_import"),
            {
                "action": "confirm",
                "rows_json": json.dumps(rows),
                "create_missing_suppliers": "on",
            },
        )
        self.assertRedirects(
            response,
            reverse("staff_parts"),
            fetch_redirect_response=False,
        )

        existing.refresh_from_db()
        self.assertEqual(existing.name, "Updated name")
        self.assertEqual(existing.quantity_on_hand, 5)
        self.assertEqual(str(existing.cost_price), "10.00")

        created = Part.objects.get(sku="NEW-1")
        self.assertEqual(created.name, "Brand new part")
        self.assertEqual(created.quantity_on_hand, 4)
        movement = created.movements.get()
        self.assertEqual(movement.kind, StockMovement.KIND_COUNT)
        self.assertEqual(movement.reason, "Opening stock from CSV import")

    def test_import_preview_reports_bad_rows(self):
        self.client.force_login(self.master)
        csv_text = (
            "sku,name,category,unit\n"
            ",Missing sku,body,each\n"
            "BAD-1,Bad category,widgets,each\n"
        )
        response = self.upload(csv_text)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["preview_rows"], [])
        self.assertTrue(response.context["errors"])
        self.assertEqual(Part.objects.count(), 0)

    def test_template_and_export_are_csv(self):
        part = self.make_part()
        self.client.force_login(self.master)

        template = self.client.get(reverse("staff_inventory_template"))
        self.assertEqual(template["Content-Type"], "text/csv")
        self.assertIn(b"opening_stock", template.content)

        export = self.client.get(reverse("staff_inventory_export"))
        self.assertEqual(export["Content-Type"], "text/csv")
        self.assertIn(part.sku.encode(), export.content)



class CustomerAccountTests(WorkTicketTestBase):
    def setUp(self):
        super().setUp()
        User = get_user_model()
        self.customer = User.objects.create_user(
            username="avery",
            password="customer-pass-123",
            first_name="Avery",
            last_name="Chen",
            email="avery@example.com",
            is_staff=False,
        )
        CustomerProfile.objects.create(user=self.customer, phone="204-555-0199")

        self.other_customer = User.objects.create_user(
            username="riley",
            password="customer-pass-456",
            first_name="Riley",
            last_name="Singh",
            email="riley@example.com",
            is_staff=False,
        )
        CustomerProfile.objects.create(user=self.other_customer, phone="204-555-0188")

        self.own_booking = BookingRequest.objects.create(
            full_name="Avery Chen",
            phone_number="204-555-0199",
            email="avery@example.com",
            customer=self.customer,
            vehicle="2018 Toyota RAV4",
            service="Windshield replacement",
            preferred_date=timezone.localdate() + timedelta(days=2),
            preferred_window="9:00–11:00 AM",
            privacy_consent=True,
        )
        self.other_booking = BookingRequest.objects.create(
            full_name="Riley Singh",
            phone_number="204-555-0188",
            email="riley@example.com",
            customer=self.other_customer,
            vehicle="2020 Ford Escape",
            service="Dent repair",
            preferred_date=timezone.localdate() + timedelta(days=3),
            preferred_window="1:00–3:00 PM",
            privacy_consent=True,
        )

    def test_customer_login_lands_on_dashboard(self):
        response = self.client.post(
            reverse("customer_login"),
            {"username": "avery", "password": "customer-pass-123"},
        )
        self.assertRedirects(
            response, reverse("customer_dashboard"), fetch_redirect_response=False
        )

    def test_unified_login_sends_customer_to_dashboard(self):
        response = self.client.post(
            reverse("login"),
            {"username": "avery", "password": "customer-pass-123"},
        )
        self.assertRedirects(
            response, reverse("customer_dashboard"), fetch_redirect_response=False
        )

    def test_unified_login_leaves_customer_out_of_staff_area(self):
        response = self.client.post(
            reverse("login"),
            {
                "username": "avery",
                "password": "customer-pass-123",
                "next": reverse("staff_dashboard"),
            },
        )
        self.assertRedirects(
            response, reverse("customer_dashboard"), fetch_redirect_response=False
        )

    def test_unified_login_honours_customer_next(self):
        response = self.client.post(
            reverse("login"),
            {
                "username": "avery",
                "password": "customer-pass-123",
                "next": reverse("customer_password_change"),
            },
        )
        self.assertRedirects(
            response,
            reverse("customer_password_change"),
            fetch_redirect_response=False,
        )

    def test_signed_in_customer_skips_login_page(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse("login"))
        self.assertRedirects(
            response, reverse("customer_dashboard"), fetch_redirect_response=False
        )

    def test_staff_login_rejects_customer_account(self):
        response = self.client.post(
            reverse("staff_login"),
            {"username": "avery", "password": "customer-pass-123"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "does not have workspace access")

    def test_customer_login_rejects_staff_account(self):
        response = self.client.post(
            reverse("customer_login"),
            {"username": "owner", "password": "owner-pass-123"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "does not have customer access")

    def test_customer_dashboard_only_shows_own_requests(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse("customer_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.own_booking.reference)
        self.assertNotContains(response, self.other_booking.reference)
        self.assertNotContains(response, "Internal notes")

    def test_customer_cannot_open_staff_area(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse("staff_dashboard"))
        self.assertRedirects(
            response, reverse("staff_login"), fetch_redirect_response=False
        )

    def test_master_creates_customer_and_links_matching_requests(self):
        BookingRequest.objects.create(
            full_name="Casey Morgan",
            phone_number="204-555-0177",
            email="casey@example.com",
            vehicle="2015 Honda Civic",
            service="Brake service",
            preferred_date=timezone.localdate() + timedelta(days=4),
            preferred_window="9:00–11:00 AM",
            privacy_consent=True,
        )
        self.client.force_login(self.master)
        response = self.client.post(
            reverse("staff_customer_create"),
            {
                "username": "casey",
                "first_name": "Casey",
                "last_name": "Morgan",
                "email": "casey@example.com",
                "phone": "204-555-0177",
                "password1": "customer-pass-789",
                "password2": "customer-pass-789",
            },
        )
        self.assertRedirects(
            response, reverse("staff_customers"), fetch_redirect_response=False
        )
        customer = get_user_model().objects.get(username="casey")
        self.assertTrue(hasattr(customer, "customer_profile"))
        self.assertEqual(
            BookingRequest.objects.get(email="casey@example.com").customer,
            customer,
        )

    def test_employee_cannot_manage_customers(self):
        self.client.force_login(self.employee)
        for name in ("staff_customers", "staff_customer_create"):
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertRedirects(
                    response,
                    reverse("staff_my_work"),
                    fetch_redirect_response=False,
                )

    def test_master_can_open_customer_admin_pages(self):
        self.client.force_login(self.master)
        pages = [
            reverse("staff_customers"),
            reverse("staff_customer_create"),
            reverse("staff_customer_edit", args=[self.customer.pk]),
            reverse("staff_customer_password", args=[self.customer.pk]),
        ]
        for url in pages:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)

    def test_customer_can_change_password(self):
        self.client.force_login(self.customer)
        response = self.client.post(
            reverse("customer_password_change"),
            {
                "old_password": "customer-pass-123",
                "new_password1": "new-customer-pass-456",
                "new_password2": "new-customer-pass-456",
            },
        )
        self.assertRedirects(
            response, reverse("customer_dashboard"), fetch_redirect_response=False
        )
        self.customer.refresh_from_db()
        self.assertTrue(self.customer.check_password("new-customer-pass-456"))

    def test_public_footer_links_customer_account(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, f'href="{reverse("login")}"')
        self.assertNotContains(response, "Customer sign in")

        self.client.force_login(self.customer)
        response = self.client.get(reverse("home"))
        self.assertContains(response, f'href="{reverse("customer_dashboard")}"')
        self.assertContains(response, ">My account<")
        self.assertNotContains(response, f'href="{reverse("login")}"')

    def test_inactive_customer_cannot_sign_in(self):
        self.customer.is_active = False
        self.customer.save(update_fields=["is_active"])
        response = self.client.post(
            reverse("customer_login"),
            {"username": "avery", "password": "customer-pass-123"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "did not match")
        self.assertNotIn("_auth_user_id", self.client.session)
        dashboard = self.client.get(reverse("customer_dashboard"))
        self.assertRedirects(
            dashboard,
            reverse("customer_login") + "?next=/account/",
            fetch_redirect_response=False,
        )

    def test_public_request_links_to_signed_in_customer(self):
        self.client.force_login(self.customer)
        response = self.client.post(
            reverse("contact"),
            {
                "full_name": "Avery Chen",
                "phone_number": "204-555-0199",
                "preferred_time": "Anytime today",
                "service_needed": "Windshield chip",
                "vehicle_description": "2018 Toyota RAV4",
            },
        )
        self.assertEqual(response.status_code, 302)
        callback = CallbackRequest.objects.latest("created_at")
        self.assertEqual(callback.customer, self.customer)

    def test_public_request_from_different_identity_is_not_linked(self):
        self.client.force_login(self.customer)
        self.client.post(
            reverse("contact"),
            {
                "full_name": "Avery Chen",
                "phone_number": "204-555-0111",
                "preferred_time": "Anytime today",
                "service_needed": "Windshield chip",
                "vehicle_description": "2018 Toyota RAV4",
            },
        )
        callback = CallbackRequest.objects.latest("created_at")
        self.assertIsNone(callback.customer)


# ---------------------------------------------------------------------------
# Repair estimator
# ---------------------------------------------------------------------------


class EstimateTestBase(TestCase):
    def setUp(self):
        cache.clear()
        from decimal import Decimal

        from mapleleaf_app.models import EstimateService, EstimateSettings

        self.settings = EstimateSettings.load()
        self.settings.site_enabled = True
        self.settings.rounding_step = 5
        self.settings.car_multiplier = Decimal("1.00")
        self.settings.suv_multiplier = Decimal("1.15")
        self.settings.luxury_multiplier = Decimal("1.40")
        self.settings.severity_minor = Decimal("1.00")
        self.settings.severity_moderate = Decimal("1.30")
        self.settings.severity_severe = Decimal("1.75")
        self.settings.save()

        self.body, _ = EstimateService.objects.update_or_create(
            slug="collision",
            defaults={
                "enabled": True,
                "base_price": Decimal("400.00"),
                "spread_percent": Decimal("20.00"),
                "unit_label": "per panel",
                "uses_severity": True,
            },
        )
        self.mechanical, _ = EstimateService.objects.update_or_create(
            slug="mechanical",
            defaults={
                "enabled": True,
                "base_price": Decimal("200.00"),
                "spread_percent": Decimal("10.00"),
                "unit_label": "per job",
                "uses_severity": False,
            },
        )

    def make_addon(self, service=None, label="Blend adjacent panel", amount="100.00", enabled=True):
        from mapleleaf_app.models import EstimateAddOn

        return EstimateAddOn.objects.create(
            service=service or self.body,
            label=label,
            amount=amount,
            enabled=enabled,
        )


class EstimatePricingTests(EstimateTestBase):
    def test_seeded_services_start_disabled_and_unpriced(self):
        from mapleleaf_app.models import EstimateService

        self.assertGreaterEqual(EstimateService.objects.count(), 10)
        self.assertFalse(EstimateService.objects.filter(enabled=True, base_price__isnull=True).exists())

    def test_range_uses_spread_vehicle_and_severity(self):
        from mapleleaf_app.estimating import price_estimate

        result = price_estimate(
            self.body,
            vehicle_class="car",
            severity="moderate",
            settings_obj=self.settings,
        )
        self.assertEqual(result.low_display, "$415")
        self.assertEqual(result.high_display, "$625")
        self.assertEqual(result.unit_label, "per panel")

    def test_rule_of_math_for_luxury_and_rounding(self):
        from decimal import Decimal

        from mapleleaf_app.estimating import price_estimate

        self.body.base_price = Decimal("1000.00")
        self.body.spread_percent = Decimal("10.00")
        self.body.uses_severity = False
        self.body.save()
        result = price_estimate(
            self.body,
            vehicle_class="luxury",
            settings_obj=self.settings,
        )
        self.assertEqual(result.low_display, "$1,260")
        self.assertEqual(result.high_display, "$1,540")

    def test_suv_multiplier_changes_both_ends(self):
        from mapleleaf_app.estimating import price_estimate

        result = price_estimate(
            self.body,
            vehicle_class="suv",
            severity="moderate",
            settings_obj=self.settings,
        )
        # 400 × 0.80 × 1.15 × 1.30 = 478.4 → 475; 400 × 1.20 × 1.15 × 1.30 = 717.6 → 720
        self.assertEqual(result.low_display, "$475")
        self.assertEqual(result.high_display, "$720")

    def test_severity_ignored_for_non_severity_service(self):
        from mapleleaf_app.estimating import price_estimate

        minor = price_estimate(self.mechanical, severity="minor", settings_obj=self.settings)
        severe = price_estimate(self.mechanical, severity="severe", settings_obj=self.settings)
        self.assertEqual(minor.range_display, severe.range_display)

    def test_addons_are_flat_on_both_ends(self):
        from mapleleaf_app.estimating import price_estimate

        addon = self.make_addon(service=self.mechanical, amount="50.00")
        result = price_estimate(
            self.mechanical,
            vehicle_class="car",
            addons=[addon],
            settings_obj=self.settings,
        )
        # 200 × 0.90 = 180 + 50 = 230; 200 × 1.10 = 220 + 50 = 270
        self.assertEqual(result.low_display, "$230")
        self.assertEqual(result.high_display, "$270")
        self.assertEqual(result.addons[0].label, "Blend adjacent panel")

    def test_disabled_service_returns_none(self):
        from mapleleaf_app.estimating import price_estimate

        self.mechanical.enabled = False
        self.mechanical.save()
        self.assertIsNone(price_estimate(self.mechanical, settings_obj=self.settings))

    def test_service_without_price_returns_none(self):
        from mapleleaf_app.estimating import price_estimate

        self.mechanical.base_price = None
        self.mechanical.save()
        self.assertIsNone(price_estimate(self.mechanical, settings_obj=self.settings))

    def test_site_switch_off_returns_none(self):
        from mapleleaf_app.estimating import price_estimate

        self.settings.site_enabled = False
        self.settings.save()
        self.assertIsNone(price_estimate(self.body, settings_obj=self.settings))

    def test_starting_price_uses_the_lowest_adjustment_floor(self):
        from mapleleaf_app.estimating import starting_price

        # Car ×1.00 and minor ×1.00 give the lowest floor: 400 × 0.80 = 320.
        self.assertEqual(starting_price(self.body, settings_obj=self.settings), 320)

    def test_starting_price_is_none_when_no_price_is_published(self):
        from mapleleaf_app.estimating import starting_price

        self.mechanical.enabled = False
        self.mechanical.save()
        self.assertIsNone(starting_price(self.mechanical, settings_obj=self.settings))

    def test_money_formats_whole_and_cents(self):
        from decimal import Decimal

        from mapleleaf_app.estimating import money

        self.assertEqual(money(Decimal("1234")), "$1,234")
        self.assertEqual(money(Decimal("1234.50")), "$1,234.50")
        self.assertEqual(money(None), "—")

    def test_enabled_service_requires_a_price_on_clean(self):
        from decimal import Decimal

        from django.core.exceptions import ValidationError

        self.mechanical.base_price = None
        with self.assertRaises(ValidationError):
            self.mechanical.full_clean()

    def test_negative_base_price_is_rejected(self):
        from decimal import Decimal

        from django.core.exceptions import ValidationError

        self.mechanical.base_price = Decimal("-1.00")
        with self.assertRaises(ValidationError):
            self.mechanical.full_clean()


class EstimatePublicViewTests(EstimateTestBase):
    def test_step_one_lists_live_and_unpriced_services(self):
        response = self.client.get(reverse("repair_estimate"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Collision repair")
        self.assertContains(response, "Not priced")
        self.assertNotContains(response, "$415")

    def test_step_one_shows_a_from_price_for_live_services(self):
        response = self.client.get(reverse("repair_estimate"))
        self.assertContains(response, "From $320")

    def test_step_two_shows_the_range(self):
        response = self.client.get(reverse("repair_estimate"), {"service": "collision"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Moderate")

        response = self.client.post(
            reverse("repair_estimate"),
            {
                "service": "collision",
                "vehicle_class": "car",
                "severity": "moderate",
                "claim_type": "private",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "$415")
        self.assertContains(response, "$625")
        self.assertContains(response, "not a quote")

    def test_non_severity_service_does_not_ask_for_damage_level(self):
        response = self.client.get(reverse("repair_estimate"), {"service": "mechanical"})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "How bad is the damage?")
        self.assertContains(response, "per job")

    def test_mpi_claim_skips_pricing_and_routes_to_navigator(self):
        response = self.client.post(
            reverse("repair_estimate"),
            {
                "service": "collision",
                "vehicle_class": "car",
                "severity": "moderate",
                "claim_type": "mpi",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "MPI settles the claim")
        self.assertContains(response, reverse("claim_navigator"))
        self.assertNotContains(response, "$415")

    def test_unknown_service_shows_a_plain_message(self):
        response = self.client.get(reverse("repair_estimate"), {"service": "not-real"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "not available right now")

    def test_unpriced_service_redirects_back_to_choices(self):
        response = self.client.get(reverse("repair_estimate"), {"service": "oil"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "not live yet")

    def test_honeypot_redirects_without_a_result(self):
        response = self.client.post(
            reverse("repair_estimate"),
            {
                "service": "collision",
                "vehicle_class": "car",
                "severity": "moderate",
                "claim_type": "private",
                "website": "http://spam.example",
            },
        )
        self.assertRedirects(response, reverse("repair_estimate"), fetch_redirect_response=False)

    def test_public_submission_writes_nothing(self):
        from mapleleaf_app.models import EstimateAddOn, EstimateService, EstimateSettings

        # First load creates the singleton settings row.
        self.client.get(reverse("repair_estimate"))
        counts = (
            EstimateService.objects.count(),
            EstimateAddOn.objects.count(),
            EstimateSettings.objects.count(),
        )
        self.client.post(
            reverse("repair_estimate"),
            {
                "service": "collision",
                "vehicle_class": "suv",
                "severity": "severe",
                "claim_type": "private",
            },
        )
        self.assertEqual(
            counts,
            (
                EstimateService.objects.count(),
                EstimateAddOn.objects.count(),
                EstimateSettings.objects.count(),
            ),
        )

    def test_site_off_shows_the_offline_state(self):
        self.settings.site_enabled = False
        self.settings.save()
        response = self.client.get(reverse("repair_estimate"))
        self.assertContains(response, "Pricing is being reviewed.")

    def test_estimate_page_is_in_the_tools_navigation(self):
        response = self.client.get(reverse("tools"))
        self.assertContains(response, reverse("repair_estimate"))


class EstimateSettingsTests(EstimateTestBase):
    def test_load_returns_a_single_row(self):
        from mapleleaf_app.models import EstimateSettings

        first = EstimateSettings.load()
        second = EstimateSettings.load()
        self.assertEqual(first.pk, 1)
        self.assertEqual(second.pk, 1)
        self.assertEqual(EstimateSettings.objects.count(), 1)

    def test_save_forces_the_singleton_pk(self):
        from mapleleaf_app.models import EstimateSettings

        EstimateSettings.objects.all().delete()
        EstimateSettings(pk=9, site_enabled=True).save()
        self.assertEqual(EstimateSettings.objects.count(), 1)
        self.assertEqual(EstimateSettings.load().pk, 1)


class EstimateStaffTests(WorkTicketTestBase):
    def setUp(self):
        super().setUp()
        from decimal import Decimal

        from mapleleaf_app.models import EstimateService, EstimateSettings

        self.settings = EstimateSettings.load()
        self.settings.site_enabled = True
        self.settings.save()
        self.service = EstimateService.objects.get(slug="collision")
        self.service.base_price = Decimal("400.00")
        self.service.spread_percent = Decimal("20.00")
        self.service.uses_severity = True
        self.service.save()

    def test_employee_cannot_open_estimator_pages(self):
        self.client.force_login(self.employee)
        for name in ("staff_estimator", "staff_estimate_settings"):
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertRedirects(
                    response,
                    reverse("staff_my_work"),
                    fetch_redirect_response=False,
                )

    def test_employee_cannot_change_a_price(self):
        self.client.force_login(self.employee)
        response = self.client.post(
            reverse("staff_estimate_edit", args=[self.service.slug]),
            {
                "enabled": "on",
                "base_price": "9999",
                "spread_percent": "20",
                "unit_label": "per panel",
            },
        )
        self.assertRedirects(
            response,
            reverse("staff_my_work"),
            fetch_redirect_response=False,
        )
        self.service.refresh_from_db()
        self.assertNotEqual(self.service.base_price, 9999)

    def test_master_can_set_and_publish_a_price(self):
        self.client.force_login(self.master)
        response = self.client.post(
            reverse("staff_estimate_edit", args=[self.service.slug]),
            {
                "enabled": "on",
                "base_price": "400",
                "spread_percent": "20",
                "unit_label": "per panel",
                "uses_severity": "on",
                "notes": "Checked against last month's tickets.",
            },
        )
        self.assertRedirects(response, reverse("staff_estimator"), fetch_redirect_response=False)
        self.service.refresh_from_db()
        self.assertTrue(self.service.is_priced)
        self.assertEqual(self.service.updated_by, self.master)

    def test_master_can_enable_an_unpriced_service_but_it_stays_call_for_pricing(self):
        self.client.force_login(self.master)
        self.service.base_price = None
        self.service.save()
        response = self.client.post(
            reverse("staff_estimate_edit", args=[self.service.slug]),
            {
                "enabled": "on",
                "spread_percent": "20",
                "unit_label": "per panel",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enter a base price before turning this estimate on.")
        self.service.refresh_from_db()
        self.assertFalse(self.service.enabled)

    def test_master_can_add_and_remove_an_addon(self):
        self.client.force_login(self.master)
        response = self.client.post(
            reverse("staff_estimate_addons", args=[self.service.slug]),
            {
                "label": "Blend adjacent panel",
                "amount": "120",
                "enabled": "on",
                "display_order": "0",
            },
        )
        self.assertRedirects(
            response,
            reverse("staff_estimate_addons", args=[self.service.slug]),
            fetch_redirect_response=False,
        )
        addon = self.service.addons.get(label="Blend adjacent panel")
        self.assertEqual(str(addon.amount), "120.00")

        response = self.client.post(
            reverse("staff_estimate_addon_delete", args=[self.service.slug, addon.pk]),
        )
        self.assertRedirects(
            response,
            reverse("staff_estimate_addons", args=[self.service.slug]),
            fetch_redirect_response=False,
        )
        self.assertFalse(self.service.addons.filter(pk=addon.pk).exists())

    def test_master_can_turn_the_whole_estimator_off(self):
        self.client.force_login(self.master)
        response = self.client.post(
            reverse("staff_estimate_settings"),
            {
                "rounding_step": "5",
                "car_multiplier": "1.00",
                "suv_multiplier": "1.15",
                "luxury_multiplier": "1.40",
                "severity_minor": "1.00",
                "severity_moderate": "1.30",
                "severity_severe": "1.75",
                "disclaimer": "Planning estimate only.",
            },
        )
        self.assertRedirects(response, reverse("staff_estimator"), fetch_redirect_response=False)
        self.settings.refresh_from_db()
        self.assertFalse(self.settings.site_enabled)
        self.assertFalse(self.settings.updated_by_id is None)

    def test_multiplier_must_be_positive(self):
        self.client.force_login(self.master)
        response = self.client.post(
            reverse("staff_estimate_settings"),
            {
                "rounding_step": "5",
                "car_multiplier": "0",
                "suv_multiplier": "1.15",
                "luxury_multiplier": "1.40",
                "severity_minor": "1.00",
                "severity_moderate": "1.30",
                "severity_severe": "1.75",
                "disclaimer": "Planning estimate only.",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "The multiplier must be greater than zero.")
