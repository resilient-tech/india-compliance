import re
from datetime import date, datetime, time, timedelta, timezone
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import frappe
import time_machine
from frappe.tests import IntegrationTestCase, change_settings
from frappe.utils import getdate

from india_compliance.exceptions import GSPServerError
from india_compliance.gst_india.constants import SHIP_TO_GSTIN_APPLICABLE_DATE, TIMEZONE
from india_compliance.gst_india.utils import (
    clear_portal_slow,
    handle_server_errors,
    is_ship_to_gstin_applicable,
    mark_portal_slow,
    portal_is_busy,
    run_after_response_or_enqueue,
    run_or_report_failure,
    validate_pincode,
)


class TestUtils(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # create old fiscal years
        fiscal_year = frappe.new_doc("Fiscal Year")
        fiscal_year.update(
            {
                "year_start_date": "2023-04-01",
                "year_end_date": "2024-03-31",
                "year": "2023-2024",
            }
        ).insert(ignore_if_duplicate=True)

        fiscal_year = frappe.new_doc("Fiscal Year")
        fiscal_year.update(
            {
                "year_start_date": "2022-04-01",
                "year_end_date": "2023-03-31",
                "year": "2022-2023",
            }
        ).insert(ignore_if_duplicate=True)

    @patch("india_compliance.gst_india.utils.getdate", return_value=getdate("2023-06-20"))
    def test_timespan_date_range(self, getdate_mock):
        from india_compliance.gst_india.utils import get_timespan_date_range

        timespan_date_range_map = {
            "this fiscal year": (date(2023, 4, 1), date(2024, 3, 31)),
            "last fiscal year": (date(2022, 4, 1), date(2023, 3, 31)),
            "this fiscal year to last month": (date(2023, 4, 1), date(2023, 5, 31)),
            "this quarter to last month": (date(2023, 4, 1), date(2023, 5, 31)),
        }

        for timespan, expected_date_range in timespan_date_range_map.items():
            actual_date_range = get_timespan_date_range(timespan)

            for i, expected_date in enumerate(expected_date_range):
                self.assertEqual(expected_date, actual_date_range[i])

    @change_settings("GST Settings", {"sandbox_mode": 0})
    def test_is_ship_to_gstin_applicable_rolls_over_in_ist(self):
        """NIC rolls over at midnight IST, whatever the site's own timezone is."""
        rollover = datetime.combine(
            SHIP_TO_GSTIN_APPLICABLE_DATE, time(), tzinfo=ZoneInfo(TIMEZONE)
        ).astimezone(timezone.utc)

        for time_zone in ("UTC", "Pacific/Kiritimati"):  # behind IST, then ahead of it
            with change_settings("System Settings", {"time_zone": time_zone}):
                with time_machine.travel(rollover - timedelta(minutes=1), tick=False):
                    self.assertFalse(is_ship_to_gstin_applicable(), time_zone)

                with time_machine.travel(rollover, tick=False):
                    self.assertTrue(is_ship_to_gstin_applicable(), time_zone)

    def test_validate_pincode(self):
        def make_address(state, pincode):
            return frappe._dict(country="India", state=state, pincode=pincode, __unsaved=True)

        for pincode in ("194101", "190015", "181101", "180007", "184101", "191401"):
            self.assertIsNone(validate_pincode(make_address("Ladakh", pincode)))
            self.assertIsNone(validate_pincode(make_address("Jammu and Kashmir", pincode)))

        for pincode in ("518503", "533347"):
            self.assertIsNone(validate_pincode(make_address("Telangana", pincode)))
            self.assertIsNone(validate_pincode(make_address("Andhra Pradesh", pincode)))

        self.assertIsNone(validate_pincode(make_address("Telangana", "500001")))

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(Postal Code .* is not associated with .*)$"),
            validate_pincode,
            make_address("Karnataka", "500001"),
        )


def in_web_request():
    """look like a request a user is waiting on"""
    return patch.object(
        frappe.local, "request", frappe._dict(method="POST", path="/api/method/generate"), create=True
    )


class TestPortalBusy(IntegrationTestCase):
    """portal_is_busy: only sheds where shedding frees a web worker"""

    def setUp(self):
        super().setUp()
        clear_portal_slow()

    def tearDown(self):
        clear_portal_slow()
        super().tearDown()

    def busy(self, inflight=0):
        with (
            patch("india_compliance.gst_india.utils.inflight_in_web", return_value=inflight),
            patch("india_compliance.gst_india.utils.max_inflight_in_web", return_value=3),
        ):
            return portal_is_busy()

    def test_healthy_portal_is_not_busy(self):
        with in_web_request():
            self.assertFalse(self.busy())

    def test_slow_portal_is_busy(self):
        mark_portal_slow()

        with in_web_request():
            self.assertTrue(self.busy())

    def test_full_web_pool_is_busy(self):
        with in_web_request():
            self.assertTrue(self.busy(inflight=3))
            self.assertFalse(self.busy(inflight=2))

    def test_worker_is_never_busy(self):
        # a queued action must not queue itself again
        mark_portal_slow()
        self.assertFalse(self.busy(inflight=99))

    def test_not_busy_once_the_response_is_out(self):
        # the worker is already committed, queueing now would only add a hop
        mark_portal_slow()

        with in_web_request(), patch.dict(frappe.flags, {"in_after_response": True}):
            self.assertFalse(self.busy(inflight=99))


class TestPortalRouting(IntegrationTestCase):
    """web worker only while the portal is healthy and the pool has room"""

    def setUp(self):
        super().setUp()
        clear_portal_slow()
        frappe.clear_messages()

    def tearDown(self):
        clear_portal_slow()
        super().tearDown()

    def route(self, is_ajax=True, inflight=0):
        action = MagicMock()
        doc = frappe._dict(doctype="Sales Invoice", name="SINV-TEST")

        with (
            in_web_request(),
            patch.object(frappe.local, "is_ajax", is_ajax, create=True),
            patch("india_compliance.gst_india.utils.inflight_in_web", return_value=inflight),
            patch("india_compliance.gst_india.utils.max_inflight_in_web", return_value=3),
            patch("frappe.enqueue") as enqueue,
        ):
            run_after_response_or_enqueue(action, doc, "failed", docname=doc.name)

        return action, enqueue

    def run_after_response(self):
        frappe.db.after_commit.run()  # inline in tests

    def test_desk_healthy_runs_after_response(self):
        action, enqueue = self.route()

        enqueue.assert_not_called()
        action.assert_not_called()  # not before the response

        self.run_after_response()
        action.assert_called_once_with(docname="SINV-TEST")

    def test_desk_slow_portal_goes_to_queue(self):
        mark_portal_slow()
        action, enqueue = self.route()

        enqueue.assert_called_once()
        self.assertEqual(enqueue.call_args.args[0], run_or_report_failure)
        self.assertEqual(enqueue.call_args.kwargs["action"], action)
        self.assertEqual(enqueue.call_args.kwargs["queue"], "short")
        self.assertEqual(enqueue.call_args.kwargs["docname"], "SINV-TEST")
        self.assertTrue(enqueue.call_args.kwargs["enqueue_after_commit"])

        self.run_after_response()
        action.assert_not_called()

    def test_desk_busy_web_pool_goes_to_queue(self):
        _, enqueue = self.route(inflight=3)

        enqueue.assert_called_once()

    def test_desk_web_pool_with_room_stays_in_web(self):
        _, enqueue = self.route(inflight=2)

        enqueue.assert_not_called()
        self.run_after_response()

    def test_outside_desk_goes_to_queue(self):
        _, enqueue = self.route(is_ajax=False)

        enqueue.assert_called_once()

    def test_dedicated_queue_when_the_bench_has_one(self):
        with patch(
            "india_compliance.gst_india.utils.get_queues_timeout",
            return_value={"short": 300, "default": 300, "long": 1500, "gst": 300},
        ):
            _, enqueue = self.route(is_ajax=False)

        self.assertEqual(enqueue.call_args.kwargs["queue"], "gst")

    def test_desk_user_is_told_it_was_queued(self):
        mark_portal_slow()
        self.route()

        self.assertIn("background", str(frappe.message_log[-1]))

    def test_no_queued_message_outside_the_desk(self):
        self.route(is_ajax=False)

        self.assertFalse(frappe.message_log)


class TestServerErrorFeedback(IntegrationTestCase):
    """handle_server_errors: every doctype hears about an outage, not just Sales Invoice"""

    def setUp(self):
        super().setUp()
        frappe.clear_messages()

    def handle(self, doctype, enable_retry=1):
        """returns (doc, message shown to the user)"""
        settings = frappe.get_cached_doc("GST Settings")
        settings.enable_retry_einv_ewb_generation = enable_retry
        doc = MagicMock()
        doc.doctype = doctype

        with (
            patch.object(settings, "db_set"),
            patch("india_compliance.gst_india.utils.notify_user") as notify,
        ):
            handle_server_errors(settings, doc, "e-Waybill", GSPServerError())

        notify.assert_called_once()
        return doc, notify.call_args.args[0]

    def test_sales_invoice_gets_status_and_retry_message(self):
        doc, message = self.handle("Sales Invoice")

        doc.db_set.assert_called_once_with({"e_waybill_status": "Auto-Retry"})
        self.assertIn("automatically retried", message)

    def test_other_doctypes_are_told_too(self):
        # no e_waybill_status field there, but silence would look like success
        doc, message = self.handle("Delivery Note")

        doc.db_set.assert_not_called()
        self.assertIn("Government services", message)
        self.assertIn("try again", message)

    def test_retry_disabled_fails_the_document(self):
        doc, message = self.handle("Sales Invoice", enable_retry=0)

        doc.db_set.assert_called_once_with({"e_waybill_status": "Failed"})
        self.assertIn("try again", message)
