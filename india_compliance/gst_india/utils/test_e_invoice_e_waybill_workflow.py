import json
from unittest.mock import patch

import frappe
from frappe.tests.test_api import FrappeAPITestCase

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
E_WAYBILL_DATA = "india_compliance.gst_india.utils.e_waybill.EWaybillData"
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


class TestEInvoiceWorkflow(FrappeAPITestCase):
    """
    Tests for e-Invoice generation workflow and error handling.
    """

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
        si = self._create_si()
        si.db_set("irn", "test_irn_12345")

        response = self._post_e_invoice(si.name, throw=True)

        self.assertEqual(response.status_code, 417)
        self.assertEqual(response.json["exc_type"], "AlreadyGeneratedError")

        # No status change for AlreadyGeneratedError
        si.reload()
        self.assertNotEqual(si.einvoice_status, "Failed")

    def test_ui_manual_not_applicable_raises(self):
        si = self._create_si()

        with patch(E_INVOICE_DATA) as mock_data:
            mock_data.side_effect = NotApplicableError("Not applicable")
            response = self._post_e_invoice(si.name, throw=True)

        self.assertEqual(response.status_code, 417)
        self.assertEqual(response.json["exc_type"], "NotApplicableError")

    def test_ui_manual_validation_error_raises(self):
        """
        Note: einvoice_status is set to 'Failed' inside the function but
        the WSGI transaction is rolled back on error, so it is not persisted.
        """
        si = self._create_si()

        with patch(E_INVOICE_DATA) as mock_data:
            mock_data.side_effect = frappe.ValidationError("Invalid HSN")
            response = self._post_e_invoice(si.name, throw=True)

        self.assertEqual(response.status_code, 417)
        self.assertEqual(response.json["exc_type"], "ValidationError")

    def test_ui_manual_mandatory_error_raises(self):
        si = self._create_si()

        with patch(E_INVOICE_DATA) as mock_data:
            mock_data.side_effect = frappe.MandatoryError("Customer Address missing")
            response = self._post_e_invoice(si.name, throw=True)

        self.assertEqual(response.status_code, 417)
        self.assertEqual(response.json["exc_type"], "MandatoryError")

    def test_ui_manual_gsp_server_error_never_raises(self):
        si = self._create_si()

        with patch(E_INVOICE_DATA) as mock_data:
            mock_data.side_effect = GSPServerError
            response = self._post_e_invoice(si.name, throw=True)

        self.assertEqual(response.status_code, 200)
        si.reload()
        self.assertEqual(si.einvoice_status, "Auto-Retry")
        frappe.db.set_single_value(
            "GST Settings", "is_retry_einv_ewb_generation_pending", 0
        )
        frappe.db.commit()  # nosemgrep

    def test_ui_manual_unhandled_exception_raises(self):
        """UI Manual: Unhandled exceptions returned as HTTP 500."""
        si = self._create_si()

        with patch(E_INVOICE_DATA) as mock_data:
            mock_data.side_effect = RuntimeError("Unexpected")
            response = self._post_e_invoice(si.name, throw=True)

        self.assertEqual(response.status_code, 500)

    # =====================================================================
    # Auto-generation UI Workflow  (throw=False, with HTTP request)
    # Client-side on_submit calls generate_e_invoice with throw=False.
    # Errors should show warnings (frappe.msgprint), not raise.
    # =====================================================================

    def test_auto_gen_ui_already_generated_skips_with_warning(self):
        si = self._create_si()
        si.db_set("irn", "test_irn_12345")

        response = self._post_e_invoice(si.name, throw=False)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(_response_message_contains(response, "already been generated"))

        si.reload()
        self.assertNotEqual(si.einvoice_status, "Failed")

    def test_auto_gen_ui_not_applicable_skips_with_message(self):
        si = self._create_si()

        with patch(E_INVOICE_DATA) as mock_data:
            mock_data.side_effect = NotApplicableError("Not applicable")
            response = self._post_e_invoice(si.name, throw=False)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(_response_message_contains(response, "Not applicable"))

        si.reload()
        self.assertNotEqual(si.einvoice_status, "Failed")

    def test_auto_gen_ui_validation_error_shows_warning(self):
        si = self._create_si()

        with patch(E_INVOICE_DATA) as mock_data:
            mock_data.side_effect = frappe.ValidationError("Invalid data")
            response = self._post_e_invoice(si.name, throw=False)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(_response_message_contains(response, "auto-generation failed"))

        si.reload()
        self.assertEqual(si.einvoice_status, "Failed")

    def test_auto_gen_ui_mandatory_error_shows_warning(self):
        si = self._create_si()

        with patch(E_INVOICE_DATA) as mock_data:
            mock_data.side_effect = frappe.MandatoryError("Missing address")
            response = self._post_e_invoice(si.name, throw=False)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(_response_message_contains(response, "auto-generation failed"))

        si.reload()
        self.assertEqual(si.einvoice_status, "Failed")

    def test_auto_gen_ui_gsp_error_shows_warning(self):
        si = self._create_si()

        with patch(E_INVOICE_DATA) as mock_data:
            mock_data.side_effect = GSPServerError
            response = self._post_e_invoice(si.name, throw=False)

        self.assertEqual(response.status_code, 200)
        si.reload()
        self.assertIn(si.einvoice_status, ("Auto-Retry", "Failed"))
        frappe.db.set_single_value(
            "GST Settings", "is_retry_einv_ewb_generation_pending", 0
        )
        frappe.db.commit()  # nosemgrep

    def test_auto_gen_ui_unhandled_exception_still_raises(self):
        si = self._create_si()

        with patch(E_INVOICE_DATA) as mock_data:
            mock_data.side_effect = RuntimeError("Unexpected")
            response = self._post_e_invoice(si.name, throw=False)

        self.assertEqual(response.status_code, 500)

    # =====================================================================
    # Auto-generation Server Workflow  (throw=False, NO request context)
    # Server-side on_submit, enqueued background job.
    # Errors should log and set status, but NOT show messages.
    # =====================================================================

    def test_auto_gen_server_already_generated(self):
        si = self._create_si()
        si.db_set("irn", "test_irn_12345")

        frappe.local.message_log = []
        with self.assertRaises(AlreadyGeneratedError):
            generate_e_invoice(si.name)

        self.assertNotEqual(si.einvoice_status, "Failed")

    def test_auto_gen_server_not_applicable(self):
        si = self._create_si()

        with patch(E_INVOICE_DATA) as mock_data:
            mock_data.side_effect = NotApplicableError("Not applicable")
            frappe.local.message_log = []
            with self.assertRaises(NotApplicableError):
                generate_e_invoice(si.name)

    def test_auto_gen_server_validation_error(self):
        si = self._create_si()

        with patch(E_INVOICE_DATA) as mock_data:
            mock_data.side_effect = frappe.ValidationError("Bad data")
            frappe.local.message_log = []
            with self.assertRaises(frappe.ValidationError):
                generate_e_invoice(si.name)

    def test_auto_gen_server_gsp_error(self):
        si = self._create_si()

        with patch(E_INVOICE_DATA) as mock_data:
            mock_data.side_effect = GSPServerError
            result = generate_e_invoice(si.name)

        self.assertIsNone(result)
        si.reload()
        self.assertIn(si.einvoice_status, ("Auto-Retry", "Failed"))
        frappe.db.set_single_value(
            "GST Settings", "is_retry_einv_ewb_generation_pending", 0
        )
        frappe.db.commit()  # nosemgrep

    def test_auto_gen_server_unhandled_exception_raises(self):
        si = self._create_si()

        with patch(E_INVOICE_DATA) as mock_data:
            mock_data.side_effect = RuntimeError("Unexpected")
            self.assertRaises(
                RuntimeError,
                generate_e_invoice,
                si.name,
            )


class TestEWaybillWorkflow(FrappeAPITestCase):
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

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.db.set_single_value("GST Settings", GST_SETTINGS)
        frappe.db.commit()  # nosemgrep

    def _create_si(self, **kwargs):
        """Create a Sales Invoice suitable for e-Waybill generation."""
        defaults = {
            "is_in_state": True,
            "company_address": "_Test Indian Registered Company-Billing",
        }
        defaults.update(kwargs)
        return create_sales_invoice(**defaults)

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
        si = self._create_si()
        si.db_set("ewaybill", "123456789012")

        response = self._post_e_waybill(
            "Sales Invoice", si.name, values={"distance": 10}
        )

        self.assertEqual(response.status_code, 417)
        self.assertEqual(response.json["exc_type"], "AlreadyGeneratedError")

    def test_ui_manual_not_applicable_raises(self):
        si = self._create_si()

        with patch(E_WAYBILL_DATA) as mock_data:
            mock_data.side_effect = NotApplicableError("Not applicable")
            response = self._post_e_waybill(
                "Sales Invoice", si.name, values={"distance": 10}
            )

        self.assertEqual(response.status_code, 417)
        self.assertEqual(response.json["exc_type"], "NotApplicableError")

    def test_ui_manual_validation_error_raises(self):
        si = self._create_si()

        with patch(E_WAYBILL_DATA) as mock_data:
            mock_data.side_effect = frappe.ValidationError("Invalid HSN")
            response = self._post_e_waybill(
                "Sales Invoice", si.name, values={"distance": 10}
            )

        self.assertEqual(response.status_code, 417)
        self.assertEqual(response.json["exc_type"], "ValidationError")

    def test_ui_manual_mandatory_error_raises(self):
        si = self._create_si()

        with patch(E_WAYBILL_DATA) as mock_data:
            mock_data.side_effect = frappe.MandatoryError("Transport details missing")
            response = self._post_e_waybill(
                "Sales Invoice", si.name, values={"distance": 10}
            )

        self.assertEqual(response.status_code, 417)
        self.assertEqual(response.json["exc_type"], "MandatoryError")

    def test_ui_manual_gsp_server_error_never_raises(self):
        si = self._create_si()

        with patch(E_WAYBILL_DATA) as mock_data:
            mock_data.side_effect = GSPServerError
            response = self._post_e_waybill(
                "Sales Invoice", si.name, values={"distance": 10}
            )

        self.assertEqual(response.status_code, 200)
        si.reload()
        self.assertEqual(si.e_waybill_status, "Auto-Retry")
        frappe.db.set_single_value(
            "GST Settings", "is_retry_einv_ewb_generation_pending", 0
        )
        frappe.db.commit()  # nosemgrep

    def test_ui_manual_unhandled_exception_raises(self):
        si = self._create_si()

        with patch(E_WAYBILL_DATA) as mock_data:
            mock_data.side_effect = RuntimeError("Unexpected")
            response = self._post_e_waybill(
                "Sales Invoice", si.name, values={"distance": 10}
            )

        self.assertEqual(response.status_code, 500)

    # =====================================================================
    # Auto-generation Workflow  (no values → throw=False)
    # Called from on_submit with no values; errors should not raise.
    # =====================================================================

    def test_auto_gen_already_generated_skips_silently(self):
        si = self._create_si()
        si.db_set("ewaybill", "123456789012")

        frappe.local.message_log = []
        _generate_e_waybill(si, throw=False)

        si.reload()
        self.assertNotEqual(si.e_waybill_status, "Failed")

    def test_auto_gen_not_applicable_skips_silently(self):
        si = self._create_si()

        with patch(E_WAYBILL_DATA) as mock_data:
            mock_data.side_effect = NotApplicableError("Not applicable")
            _generate_e_waybill(si, throw=False)

        si.reload()
        self.assertEqual(si.e_waybill_status, "Not Applicable")

    def test_auto_gen_validation_error_sets_failed(self):
        si = self._create_si()

        with patch(E_WAYBILL_DATA) as mock_data:
            mock_data.side_effect = frappe.ValidationError("Invalid data")
            _generate_e_waybill(si, throw=False)

        si.reload()
        self.assertEqual(si.e_waybill_status, "Failed")

    def test_auto_gen_mandatory_error_sets_failed(self):
        si = self._create_si()

        with patch(E_WAYBILL_DATA) as mock_data:
            mock_data.side_effect = frappe.MandatoryError("Missing transport details")
            _generate_e_waybill(si, throw=False)

        si.reload()
        self.assertEqual(si.e_waybill_status, "Failed")

    def test_auto_gen_gsp_error_sets_status(self):
        si = self._create_si()

        with patch(E_WAYBILL_DATA) as mock_data:
            mock_data.side_effect = GSPServerError
            _generate_e_waybill(si, throw=False)

        si.reload()
        self.assertIn(si.e_waybill_status, ("Auto-Retry", "Failed"))
        frappe.db.set_single_value(
            "GST Settings", "is_retry_einv_ewb_generation_pending", 0
        )
        frappe.db.commit()  # nosemgrep

    def test_auto_gen_unhandled_exception_always_raises(self):
        si = self._create_si()

        with patch(E_WAYBILL_DATA) as mock_data:
            mock_data.side_effect = RuntimeError("Unexpected")
            self.assertRaises(
                RuntimeError,
                _generate_e_waybill,
                si,
                throw=False,
            )

        si.reload()
        self.assertEqual(si.e_waybill_status, "Failed")


class TestBulkGeneration(FrappeAPITestCase):
    """
    Tests for bulk e-Invoice and e-Waybill generation behavior.

    Bulk generation iterates over multiple documents, logging errors
    for each failed document and continuing to the next.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.db.set_single_value("GST Settings", GST_SETTINGS)
        frappe.db.commit()  # nosemgrep

    def _create_si(self, **kwargs):
        defaults = {
            "is_in_state": True,
            "company_address": "_Test Indian Registered Company-Billing",
        }
        defaults.update(kwargs)
        return create_sales_invoice(**defaults)

    # =====================================================================
    # e-Invoice Bulk Generation
    # =====================================================================

    @check_error_logged_for_doc(no_logs=True)
    def test_einvoice_bulk_all_succeed(self):
        """Bulk e-Invoice: all documents processed successfully."""
        si1 = self._create_si()
        si2 = self._create_si()

        with patch(E_INVOICE_API) as mock_gen:
            mock_gen.return_value = None
            generate_e_invoices([si1.name, si2.name])

        self.assertEqual(mock_gen.call_count, 2)

    @check_error_logged_for_doc("Sales Invoice", "Error for si1")
    def test_einvoice_bulk_first_fails_second_succeeds(self):
        si1 = self._create_si()
        si2 = self._create_si()

        with patch(E_INVOICE_API) as mock_gen:
            mock_gen.side_effect = [
                frappe.ValidationError("Error for si1"),
                None,
            ]
            generate_e_invoices([si1.name, si2.name])

        self.assertEqual(mock_gen.call_count, 2)

    @check_error_logged_for_doc("Sales Invoice", "Error for si1")
    @check_error_logged_for_doc("Sales Invoice", "Error for si2")
    def test_einvoice_bulk_all_fail(self):
        """Bulk e-Invoice: all documents fail, no exception raised to caller."""
        si1 = self._create_si()
        si2 = self._create_si()

        with patch(E_INVOICE_API) as mock_gen:
            mock_gen.side_effect = [
                frappe.ValidationError("Error for si1"),
                frappe.ValidationError("Error for si2"),
            ]
            generate_e_invoices([si1.name, si2.name])

        self.assertEqual(mock_gen.call_count, 2)

    @check_error_logged_for_doc(no_logs=True)
    def test_einvoice_bulk_gsp_error_continues(self):
        """Bulk e-Invoice: GSPServerError for one doc doesn't stop others."""
        si1 = self._create_si()
        si2 = self._create_si()

        with patch(E_INVOICE_IRN_GENERATION_API) as mock_gen:
            mock_gen.side_effect = [GSPServerError, None]
            generate_e_invoices([si1.name, si2.name])

        self.assertEqual(mock_gen.call_count, 1)

    @check_error_logged_for_doc("Sales Invoice", "Unexpected")
    def test_einvoice_bulk_runtime_error_continues(self):
        """Bulk e-Invoice: unhandled exceptions are logged, processing continues."""
        si1 = self._create_si()
        si2 = self._create_si()

        with patch(E_INVOICE_API) as mock_gen:
            mock_gen.side_effect = [
                RuntimeError("Unexpected"),
                None,
            ]
            generate_e_invoices([si1.name, si2.name])

        self.assertEqual(mock_gen.call_count, 2)

    # =====================================================================
    # e-Waybill Bulk Generation
    # =====================================================================

    @check_error_logged_for_doc(no_logs=True)
    def test_ewaybill_bulk_all_succeed(self):
        """Bulk e-Waybill: all documents processed successfully."""
        si1 = self._create_si()
        si2 = self._create_si()

        with patch(E_WAYBILL_GENERATE) as mock_gen:
            mock_gen.return_value = None
            generate_e_waybills("Sales Invoice", [si1.name, si2.name])

        self.assertEqual(mock_gen.call_count, 2)

    @check_error_logged_for_doc("Sales Invoice", "Error for si1")
    def test_ewaybill_bulk_first_fails_second_succeeds(self):
        """Bulk e-Waybill: first doc fails, second still processed."""
        si1 = self._create_si()
        si2 = self._create_si()

        with patch(E_WAYBILL_GENERATE) as mock_gen:
            mock_gen.side_effect = [
                frappe.ValidationError("Error for si1"),
                None,
            ]
            generate_e_waybills("Sales Invoice", [si1.name, si2.name])

        self.assertEqual(mock_gen.call_count, 2)

    @check_error_logged_for_doc("Sales Invoice", "Error for si1")
    @check_error_logged_for_doc("Sales Invoice", "Error for si2")
    def test_ewaybill_bulk_all_fail(self):
        """Bulk e-Waybill: all documents fail, no exception raised to caller."""
        si1 = self._create_si()
        si2 = self._create_si()

        with patch(E_WAYBILL_GENERATE) as mock_gen:
            mock_gen.side_effect = [
                frappe.ValidationError("Error for si1"),
                frappe.ValidationError("Error for si2"),
            ]
            generate_e_waybills("Sales Invoice", [si1.name, si2.name])

        self.assertEqual(mock_gen.call_count, 2)

    @check_error_logged_for_doc(no_logs=True)
    def test_ewaybill_bulk_gsp_error_continues(self):
        """Bulk e-Waybill: GSPServerError for one doc doesn't stop others."""
        si1 = self._create_si()
        si2 = self._create_si()

        with patch(E_WAYBILL_DATA) as mock_data:
            mock_data.side_effect = None

            with patch(E_WAYBILL_GENERATE_API) as mock_gen:
                mock_gen.side_effect = [
                    GSPServerError,
                    None,
                ]
                generate_e_waybills("Sales Invoice", [si1.name, si2.name])

        self.assertEqual(mock_gen.call_count, 1)

    @check_error_logged_for_doc("Sales Invoice", "Unexpected")
    def test_ewaybill_bulk_runtime_error_continues(self):
        """Bulk e-Waybill: unhandled exceptions are logged, processing continues."""
        si1 = self._create_si()
        si2 = self._create_si()

        with patch(E_WAYBILL_GENERATE) as mock_gen:
            mock_gen.side_effect = [
                RuntimeError("Unexpected"),
                None,
            ]
            generate_e_waybills("Sales Invoice", [si1.name, si2.name])

        self.assertEqual(mock_gen.call_count, 2)
