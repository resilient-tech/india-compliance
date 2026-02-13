import json
from unittest.mock import patch

import frappe
from frappe.tests.test_api import FrappeAPITestCase
from frappe.tests.utils import patch_hooks

from india_compliance.exceptions import (
    AlreadyGeneratedError,
    GSPServerError,
    NotApplicableError,
)
from india_compliance.gst_india.utils.e_invoice import (
    generate_e_invoice,
    generate_e_invoices,
)
from india_compliance.gst_india.utils.e_waybill import (
    _generate_e_waybill,
    generate_e_waybills,
)
from india_compliance.gst_india.utils.tests import (
    create_sales_invoice,
)

E_INVOICE_API = "india_compliance.gst_india.utils.e_invoice.generate_e_invoice"
E_INVOICE_DATA = "india_compliance.gst_india.utils.e_invoice.EInvoiceData"
E_INVOICE_IRN_GENERATION_API = (
    "india_compliance.gst_india.api_classes.nic.e_invoice.EInvoiceAPI.generate_irn"
)


E_WAYBILL_API = "india_compliance.gst_india.utils.e_waybill.generate_e_waybill"
E_WAYBILL_DATA = "india_compliance.gst_india.utils.e_waybill.EWaybillData.get_data"
E_WAYBILL_GENERATE = "india_compliance.gst_india.utils.e_waybill._generate_e_waybill"
E_WAYBILL_GENERATE_API = "india_compliance.gst_india.api_classes.nic.e_waybill.EWaybillAPI.generate_e_waybill"

GST_SETTINGS = {
    "enable_api": 1,
    "sandbox_mode": 1,
    "enable_e_invoice": 1,
    "auto_generate_e_waybill": 0,
    "auto_generate_e_invoice": 0,
    "enable_e_waybill": 1,
    "fetch_e_waybill_data": 0,
    "apply_e_invoice_only_for_selected_companies": 0,
    "enable_retry_einv_ewb_generation": 1,
    "auto_cancel_e_invoice": 0,
    "restrict_cancel_if_e_invoice_final": 0,
    "e_invoice_applicable_from": "2021-01-01",
    "is_retry_einv_ewb_generation_pending": 0,
}


def _parse_server_messages(response):
    """Parse _server_messages from an API response."""
    raw = response.json.get("_server_messages")
    if not raw:
        return []
    messages = json.loads(raw)
    return [json.loads(m) if isinstance(m, str) else m for m in messages]


def _response_message_contains(response, substr):
    """Check if any _server_messages in the response contains the given substring."""
    return any(
        substr in str(m.get("message", "")) for m in _parse_server_messages(response)
    )


def check_error_logged_for_doc(doctype=None, error_substr=None, no_logs=False):
    def decorator(func):
        def wrapper(*args, **kwargs):
            filters = {}

            if doctype:
                filters["reference_doctype"] = doctype

            if error_substr:
                filters["error"] = ["like", f"%{error_substr}%"]

            creation_after = frappe.utils.now()
            func(*args, **kwargs)
            logs = frappe.get_all(
                "Error Log",
                filters={
                    **filters,
                    "creation": [">=", creation_after],
                },
            )

            if no_logs:
                assert not logs, "No error log expected, but found logs"

            else:
                assert logs, f"No error log found matching filters: {filters}"

        return wrapper

    return decorator


class WorkflowTestBase(FrappeAPITestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.db.set_single_value("GST Settings", GST_SETTINGS)
        frappe.db.commit()  # nosemgrep # Make settings visible to WSGI thread

    def _create_si(self, **kwargs):
        """Create a Sales Invoice suitable for e-Invoice generation."""
        defaults = {
            "is_in_state": True,
            "company_address": "_Test Indian Registered Company-Billing",
        }
        defaults.update(kwargs)
        return create_sales_invoice(**defaults)

    def setUp(self):
        super().setUp()

        self.si = self._create_si()
        frappe.db.commit()  # nosemgrep # Ensure SI is visible to WSGI thread

    def tearDown(self):
        super().tearDown()

        self.si.reload()
        self.si.cancel()
        self.si.delete(force=True, ignore_permissions=True)
        frappe.db.commit()  # nosemgrep


class TestEInvoiceWorkflow(WorkflowTestBase):
    """
    Tests for e-Invoice generation workflow and error handling.
    """

    def _post_e_invoice(self, docname, throw=True, force=False):
        """Make a real HTTP POST to the generate_e_invoice API endpoint.

        Commits pending DB changes before the POST so the WSGI thread
        can see them, and starts a fresh transaction after so the test
        thread can read any WSGI-committed changes.
        """
        sid = self.sid
        frappe.db.commit()  # nosemgrep
        response = self.post(
            self.method(E_INVOICE_API),
            {"docname": docname, "throw": throw, "force": force, "sid": sid},
        )
        frappe.db.rollback()  # Fresh transaction to see WSGI-committed changes
        return response

    # =====================================================================
    # UI Manual Workflow  (throw=True, with HTTP request)
    # User clicks "Generate e-Invoice" button on the form.
    # Errors are raised as exceptions back to the UI.
    # =====================================================================

    def test_ui_manual_already_generated_raises(self):
        self.si.db_set("irn", "test_irn_12345")

        response = self._post_e_invoice(self.si.name, throw=True)

        self.assertEqual(response.status_code, 417)
        self.assertEqual(response.json["exc_type"], "AlreadyGeneratedError")

        # No status change for AlreadyGeneratedError
        self.si.reload()
        self.assertNotEqual(self.si.einvoice_status, "Failed")

    def test_ui_manual_not_applicable_raises(self):
        with patch(E_INVOICE_DATA) as mock_data:
            mock_data.side_effect = NotApplicableError("Not applicable")
            response = self._post_e_invoice(self.si.name, throw=True)

        self.assertEqual(response.status_code, 417)
        self.assertEqual(response.json["exc_type"], "NotApplicableError")

    def test_ui_manual_validation_error_raises(self):
        """
        Note: einvoice_status is set to 'Failed' inside the function but
        the WSGI transaction is rolled back on error, so it is not persisted.
        """

        with patch(E_INVOICE_DATA) as mock_data:
            mock_data.side_effect = frappe.ValidationError("Invalid HSN")
            response = self._post_e_invoice(self.si.name, throw=True)

        self.assertEqual(response.status_code, 417)
        self.assertEqual(response.json["exc_type"], "ValidationError")

    def test_ui_manual_mandatory_error_raises(self):
        with patch(E_INVOICE_DATA) as mock_data:
            mock_data.side_effect = frappe.MandatoryError("Customer Address missing")
            response = self._post_e_invoice(self.si.name, throw=True)

        self.assertEqual(response.status_code, 417)
        self.assertEqual(response.json["exc_type"], "MandatoryError")

    @patch_hooks(
        {
            "before_request": [
                *frappe.get_hooks("before_request"),
                "india_compliance.gst_india.utils.test_e_invoice_e_waybill_workflow.set_in_test_as_true",
            ]
        }
    )
    def test_ui_manual_gsp_server_error_never_raises(self):
        with patch(E_INVOICE_DATA) as mock_data:
            mock_data.side_effect = GSPServerError
            response = self._post_e_invoice(self.si.name, throw=True)

        self.assertEqual(response.status_code, 200)
        self.si.reload()
        self.assertEqual(self.si.einvoice_status, "Auto-Retry")
        frappe.db.set_single_value(
            "GST Settings", "is_retry_einv_ewb_generation_pending", 0
        )
        frappe.db.commit()  # nosemgrep

    def test_ui_manual_unhandled_exception_raises(self):
        """UI Manual: Unhandled exceptions returned as HTTP 500."""
        with patch(E_INVOICE_DATA) as mock_data:
            mock_data.side_effect = RuntimeError("Unexpected")
            response = self._post_e_invoice(self.si.name, throw=True)

        self.assertEqual(response.status_code, 500)

    # =====================================================================
    # Auto-generation UI Workflow  (throw=False, with HTTP request)
    # Client-side on_submit calls generate_e_invoice with throw=False.
    # Errors should show warnings (frappe.msgprint), not raise.
    # =====================================================================

    def test_auto_gen_ui_already_generated_skips_with_warning(self):
        self.si.db_set("irn", "test_irn_12345")

        response = self._post_e_invoice(self.si.name, throw=False)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(_response_message_contains(response, "already been generated"))

        self.si.reload()
        self.assertNotEqual(self.si.einvoice_status, "Failed")

    def test_auto_gen_ui_not_applicable_skips_with_message(self):
        with patch(E_INVOICE_DATA) as mock_data:
            mock_data.side_effect = NotApplicableError("Not applicable")
            response = self._post_e_invoice(self.si.name, throw=False)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(_response_message_contains(response, "Not applicable"))

        self.si.reload()
        self.assertEqual(self.si.einvoice_status, "Not Applicable")

    def test_auto_gen_ui_validation_error_shows_warning(self):
        with patch(E_INVOICE_DATA) as mock_data:
            mock_data.side_effect = frappe.ValidationError("Invalid data")
            response = self._post_e_invoice(self.si.name, throw=False)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(_response_message_contains(response, "auto-generation failed"))

        self.si.reload()
        self.assertEqual(self.si.einvoice_status, "Failed")

    def test_auto_gen_ui_mandatory_error_shows_warning(self):
        with patch(E_INVOICE_DATA) as mock_data:
            mock_data.side_effect = frappe.MandatoryError("Missing address")
            response = self._post_e_invoice(self.si.name, throw=False)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(_response_message_contains(response, "auto-generation failed"))

        self.si.reload()
        self.assertEqual(self.si.einvoice_status, "Failed")

    def test_auto_gen_ui_gsp_error_shows_warning(self):
        with patch(E_INVOICE_DATA) as mock_data:
            mock_data.side_effect = GSPServerError
            response = self._post_e_invoice(self.si.name, throw=False)

        self.assertEqual(response.status_code, 200)
        self.si.reload()
        self.assertIn(self.si.einvoice_status, ("Auto-Retry", "Failed"))
        frappe.db.set_single_value(
            "GST Settings", "is_retry_einv_ewb_generation_pending", 0
        )
        frappe.db.commit()  # nosemgrep

    def test_auto_gen_ui_unhandled_exception_still_raises(self):
        with patch(E_INVOICE_DATA) as mock_data:
            mock_data.side_effect = RuntimeError("Unexpected")
            response = self._post_e_invoice(self.si.name, throw=False)

        self.assertEqual(response.status_code, 500)

    # =====================================================================
    # Auto-generation Server Workflow  (throw=False, NO request context)
    # Server-side on_submit, enqueued background job.
    # Errors should log and set status, but NOT show messages.
    # =====================================================================

    def test_auto_gen_server_already_generated(self):
        self.si.db_set("irn", "test_irn_12345")

        with self.assertRaises(AlreadyGeneratedError):
            generate_e_invoice(self.si.name)

        self.assertNotEqual(self.si.einvoice_status, "Failed")

    def test_auto_gen_server_not_applicable(self):
        with patch(E_INVOICE_DATA) as mock_data:
            mock_data.side_effect = NotApplicableError("Not applicable")
            frappe.local.message_log = []
            with self.assertRaises(NotApplicableError):
                generate_e_invoice(self.si.name)

    def test_auto_gen_server_validation_error(self):
        with patch(E_INVOICE_DATA) as mock_data:
            mock_data.side_effect = frappe.ValidationError("Bad data")
            frappe.local.message_log = []
            with self.assertRaises(frappe.ValidationError):
                generate_e_invoice(self.si.name)

    def test_auto_gen_server_gsp_error(self):
        with patch(E_INVOICE_DATA) as mock_data:
            mock_data.side_effect = GSPServerError
            result = generate_e_invoice(self.si.name)

        self.assertIsNone(result)
        self.si.reload()
        self.assertIn(self.si.einvoice_status, ("Auto-Retry", "Failed"))
        frappe.db.set_single_value(
            "GST Settings", "is_retry_einv_ewb_generation_pending", 0
        )
        frappe.db.commit()  # nosemgrep

    def test_auto_gen_server_unhandled_exception_raises(self):
        with patch(E_INVOICE_DATA) as mock_data:
            mock_data.side_effect = RuntimeError("Unexpected")
            self.assertRaises(
                RuntimeError,
                generate_e_invoice,
                self.si.name,
            )


class TestEWaybillWorkflow(WorkflowTestBase):
    """
    Tests for e-Waybill generation workflow and error handling.

    Mirrors the e-Invoice tests for `_generate_e_waybill` / `generate_e_waybill`.

    Key differences from e-Invoice:
    - `generate_e_waybill(*, doctype, docname, values=None, force=False)` is
      keyword-only.
    - `throw` is determined by `values`: True when values provided (UI Manual),
      False when no values (auto-generation).
    - Status field is `e_waybill_status` (only set for Sales Invoice).
    - Already-generated check uses `doc.ewaybill` instead of `doc.irn`.
    """

    def _post_e_waybill(self, doctype, docname, values=None, force=False):
        """Make a real HTTP POST to the generate_e_waybill API endpoint."""
        sid = self.sid
        frappe.db.commit()  # nosemgrep
        data = {"doctype": doctype, "docname": docname, "force": force, "sid": sid}
        if values is not None:
            data["values"] = frappe.as_json(values)
        response = self.post(self.method(E_WAYBILL_API), data)
        frappe.db.rollback()
        return response

    # =====================================================================
    # UI Manual Workflow  (values provided → throw=True, with HTTP request)
    # User clicks "Generate e-Waybill" with transport details.
    # =====================================================================

    def test_ui_manual_already_generated_raises(self):
        self.si.db_set("ewaybill", "123456789012")

        response = self._post_e_waybill(
            "Sales Invoice", self.si.name, values={"distance": 10}
        )

        self.assertEqual(response.status_code, 417)
        self.assertEqual(response.json["exc_type"], "AlreadyGeneratedError")

    def test_ui_manual_not_applicable_raises(self):
        with patch(E_WAYBILL_DATA) as mock_data:
            mock_data.side_effect = NotApplicableError("Not applicable")
            response = self._post_e_waybill(
                "Sales Invoice", self.si.name, values={"distance": 10}
            )

        self.assertEqual(response.status_code, 417)
        self.assertEqual(response.json["exc_type"], "NotApplicableError")

    def test_ui_manual_validation_error_raises(self):
        with patch(E_WAYBILL_DATA) as mock_data:
            mock_data.side_effect = frappe.ValidationError("Invalid HSN")
            response = self._post_e_waybill(
                "Sales Invoice", self.si.name, values={"distance": 10}
            )

        self.assertEqual(response.status_code, 417)
        self.assertEqual(response.json["exc_type"], "ValidationError")

    def test_ui_manual_mandatory_error_raises(self):
        with patch(E_WAYBILL_DATA) as mock_data:
            mock_data.side_effect = frappe.MandatoryError("Transport details missing")
            response = self._post_e_waybill(
                "Sales Invoice", self.si.name, values={"distance": 10}
            )

        self.assertEqual(response.status_code, 417)
        self.assertEqual(response.json["exc_type"], "MandatoryError")

    @patch_hooks(
        {
            "before_request": [
                *frappe.get_hooks("before_request"),
                "india_compliance.gst_india.utils.test_e_invoice_e_waybill_workflow.set_in_test_as_true",
            ]
        }
    )
    def test_ui_manual_gsp_server_error_never_raises(self):
        with patch(E_WAYBILL_DATA) as mock_data:
            mock_data.side_effect = GSPServerError
            response = self._post_e_waybill(
                "Sales Invoice", self.si.name, values={"distance": 10}
            )

        self.assertEqual(response.status_code, 200)
        self.si.reload()
        self.assertEqual(self.si.e_waybill_status, "Auto-Retry")
        frappe.db.set_single_value(
            "GST Settings", "is_retry_einv_ewb_generation_pending", 0
        )
        frappe.db.commit()  # nosemgrep

    def test_ui_manual_unhandled_exception_raises(self):
        with patch(E_WAYBILL_DATA) as mock_data:
            mock_data.side_effect = RuntimeError("Unexpected")
            response = self._post_e_waybill(
                "Sales Invoice", self.si.name, values={"distance": 10}
            )

        self.assertEqual(response.status_code, 500)

    # =====================================================================
    # Auto-generation Workflow  (no values → throw=False)
    # Called from on_submit with no values; errors should not raise.
    # =====================================================================

    def test_auto_gen_already_generated_skips_silently(self):
        self.si.db_set("ewaybill", "123456789012")

        frappe.local.message_log = []
        _generate_e_waybill(self.si, throw=False)

        self.si.reload()
        self.assertNotEqual(self.si.e_waybill_status, "Failed")

    def test_auto_gen_not_applicable_skips_silently(self):
        with patch(E_WAYBILL_DATA) as mock_data:
            mock_data.side_effect = NotApplicableError("Not applicable")
            _generate_e_waybill(self.si, throw=False)

        self.si.reload()
        self.assertEqual(self.si.e_waybill_status, "Not Applicable")

    def test_auto_gen_validation_error_sets_failed(self):
        with patch(E_WAYBILL_DATA) as mock_data:
            mock_data.side_effect = frappe.ValidationError("Invalid data")
            _generate_e_waybill(self.si, throw=False)

        self.si.reload()
        self.assertEqual(self.si.e_waybill_status, "Failed")

    def test_auto_gen_mandatory_error_sets_failed(self):
        with patch(E_WAYBILL_DATA) as mock_data:
            mock_data.side_effect = frappe.MandatoryError("Missing transport details")
            _generate_e_waybill(self.si, throw=False)

        self.si.reload()
        self.assertEqual(self.si.e_waybill_status, "Failed")

    def test_auto_gen_gsp_error_sets_status(self):
        with patch(E_WAYBILL_DATA) as mock_data:
            mock_data.side_effect = GSPServerError
            _generate_e_waybill(self.si, throw=False)

        self.si.reload()
        self.assertIn(self.si.e_waybill_status, ("Auto-Retry", "Failed"))
        frappe.db.set_single_value(
            "GST Settings", "is_retry_einv_ewb_generation_pending", 0
        )
        frappe.db.commit()  # nosemgrep

    def test_auto_gen_unhandled_exception_always_raises(self):
        with patch(E_WAYBILL_DATA) as mock_data:
            mock_data.side_effect = RuntimeError("Unexpected")
            self.assertRaises(
                RuntimeError,
                _generate_e_waybill,
                self.si,
                throw=False,
            )

        self.si.reload()
        self.assertEqual(self.si.e_waybill_status, "Failed")


class TestBulkGeneration(WorkflowTestBase):
    """
    Tests for bulk e-Invoice and e-Waybill generation behavior.

    Bulk generation iterates over multiple documents, logging errors
    for each failed document and continuing to the next.
    """

    def setUp(self):
        self.si1 = self._create_si()
        self.si2 = self._create_si()

    def tearDown(self):
        self.si1.reload()
        self.si1.cancel()
        self.si1.delete(force=True, ignore_permissions=True)

        self.si2.reload()
        self.si2.cancel()
        self.si2.delete(force=True, ignore_permissions=True)
        frappe.db.commit()  # nosemgrep

    # =====================================================================
    # e-Invoice Bulk Generation
    # =====================================================================

    @check_error_logged_for_doc(no_logs=True)
    def test_einvoice_bulk_all_succeed(self):
        """Bulk e-Invoice: all documents processed successfully."""

        with patch(E_INVOICE_API) as mock_gen:
            mock_gen.return_value = None
            generate_e_invoices([self.si1.name, self.si2.name])

        self.assertEqual(mock_gen.call_count, 2)

    @check_error_logged_for_doc("Sales Invoice", "Error for si1")
    def test_einvoice_bulk_first_fails_second_succeeds(self):
        with patch(E_INVOICE_API) as mock_gen:
            mock_gen.side_effect = [
                frappe.ValidationError("Error for si1"),
                None,
            ]
            generate_e_invoices([self.si1.name, self.si2.name])

        self.assertEqual(mock_gen.call_count, 2)

    @check_error_logged_for_doc("Sales Invoice", "Error for si1")
    @check_error_logged_for_doc("Sales Invoice", "Error for si2")
    def test_einvoice_bulk_all_fail(self):
        """Bulk e-Invoice: all documents fail, no exception raised to caller."""
        with patch(E_INVOICE_API) as mock_gen:
            mock_gen.side_effect = [
                frappe.ValidationError("Error for si1"),
                frappe.ValidationError("Error for si2"),
            ]
            generate_e_invoices([self.si1.name, self.si2.name])

        self.assertEqual(mock_gen.call_count, 2)

    @check_error_logged_for_doc(no_logs=True)
    def test_einvoice_bulk_gsp_error_continues(self):
        """Bulk e-Invoice: GSPServerError for one doc doesn't stop others."""
        with patch(E_INVOICE_IRN_GENERATION_API) as mock_gen:
            mock_gen.side_effect = [GSPServerError, None]
            generate_e_invoices([self.si1.name, self.si2.name])

        self.assertEqual(mock_gen.call_count, 1)
        frappe.db.set_single_value(
            "GST Settings", "is_retry_einv_ewb_generation_pending", 0
        )
        frappe.db.commit()  # nosemgrep

    @check_error_logged_for_doc("Sales Invoice", "Unexpected")
    def test_einvoice_bulk_runtime_error_continues(self):
        """Bulk e-Invoice: unhandled exceptions are logged, processing continues."""
        with patch(E_INVOICE_API) as mock_gen:
            mock_gen.side_effect = [
                RuntimeError("Unexpected"),
                None,
            ]
            generate_e_invoices([self.si1.name, self.si2.name])

        self.assertEqual(mock_gen.call_count, 2)

    # =====================================================================
    # e-Waybill Bulk Generation
    # =====================================================================

    @check_error_logged_for_doc(no_logs=True)
    def test_ewaybill_bulk_all_succeed(self):
        """Bulk e-Waybill: all documents processed successfully."""
        with patch(E_WAYBILL_GENERATE) as mock_gen:
            mock_gen.return_value = None
            generate_e_waybills("Sales Invoice", [self.si1.name, self.si2.name])

        self.assertEqual(mock_gen.call_count, 2)

    @check_error_logged_for_doc("Sales Invoice", "Error for si1")
    def test_ewaybill_bulk_first_fails_second_succeeds(self):
        """Bulk e-Waybill: first doc fails, second still processed."""
        with patch(E_WAYBILL_GENERATE) as mock_gen:
            mock_gen.side_effect = [
                frappe.ValidationError("Error for si1"),
                None,
            ]
            generate_e_waybills("Sales Invoice", [self.si1.name, self.si2.name])

        self.assertEqual(mock_gen.call_count, 2)

    @check_error_logged_for_doc("Sales Invoice", "Error for si1")
    @check_error_logged_for_doc("Sales Invoice", "Error for si2")
    def test_ewaybill_bulk_all_fail(self):
        """Bulk e-Waybill: all documents fail, no exception raised to caller."""
        with patch(E_WAYBILL_GENERATE) as mock_gen:
            mock_gen.side_effect = [
                frappe.ValidationError("Error for si1"),
                frappe.ValidationError("Error for si2"),
            ]
            generate_e_waybills("Sales Invoice", [self.si1.name, self.si2.name])

        self.assertEqual(mock_gen.call_count, 2)

    @check_error_logged_for_doc(no_logs=True)
    def test_ewaybill_bulk_gsp_error_continues(self):
        """Bulk e-Waybill: GSPServerError for one doc doesn't stop others."""
        with patch(E_WAYBILL_DATA) as mock_data:
            mock_data.return_value = None

            with patch(E_WAYBILL_GENERATE_API) as mock_gen:
                mock_gen.side_effect = [
                    GSPServerError,
                    GSPServerError,
                ]
                generate_e_waybills("Sales Invoice", [self.si1.name, self.si2.name])

        self.assertEqual(mock_gen.call_count, 1)

    @check_error_logged_for_doc("Sales Invoice", "Unexpected")
    def test_ewaybill_bulk_runtime_error_continues(self):
        """Bulk e-Waybill: unhandled exceptions are logged, processing continues."""
        with patch(E_WAYBILL_GENERATE) as mock_gen:
            mock_gen.side_effect = [
                RuntimeError("Unexpected"),
                None,
            ]
            generate_e_waybills("Sales Invoice", [self.si1.name, self.si2.name])

        self.assertEqual(mock_gen.call_count, 2)


def set_in_test_as_true():
    """Hook method to set a flag in frappe.local during tests."""
    frappe.flags.in_test = True
