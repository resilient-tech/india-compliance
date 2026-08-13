from contextlib import contextmanager
from pathlib import Path
from typing import ClassVar
from unittest.mock import patch

import frappe
from frappe.database.schema import add_column
from frappe.modules.patch_handler import get_patches_from_app
from frappe.tests import IntegrationTestCase, change_settings

from india_compliance.gst_india.doctype.bill_of_entry.bill_of_entry import (
    make_bill_of_entry,
)
from india_compliance.gst_india.utils.tests import (
    create_purchase_invoice,
    create_sales_invoice,
)
from india_compliance.install import POST_INSTALL_PATCHES


class TestPatches(IntegrationTestCase):
    @patch(
        "india_compliance.patches.v16.update_reconciliation_email_template_dates.frappe.get_all",
        return_value=[],
    )
    @patch(
        "india_compliance.patches.v16.update_reconciliation_email_template_dates.frappe.db.has_column",
        return_value=False,
    )
    def test_reconciliation_email_patch_without_reference_doctype(self, has_column, get_all):
        from india_compliance.patches.v16.update_reconciliation_email_template_dates import execute

        execute()

        has_column.assert_called_once_with("Email Template", "reference_doctype")
        get_all.assert_called_once_with(
            "Email Template",
            or_filters={"name": "Purchase Reconciliation"},
            fields=("name", "subject", "response", "response_html"),
        )

    def test_post_install_patch_exists(self):
        for patch in POST_INSTALL_PATCHES:
            self.assertTrue(frappe.get_attr(f"india_compliance.patches.post_install.{patch}.execute"))

    def test_patches_exists(self):
        patches = get_patches_from_app("india_compliance")

        for patch in patches:
            if patch.startswith("execute:"):
                import_path = patch.split("execute:")[1]

                if not import_path.startswith("from"):
                    continue

                components = import_path.split("from")[1].split()
                module = components[0]
                function_name = components[2].replace(";", "").replace(",", "")
                patch_path = module + "." + function_name
            else:
                patch_path = f"{patch.split(maxsplit=1)[0]}.execute"

            frappe.get_attr(patch_path)

    #: Recreate the columns so the query actually executes.
    LEGACY_COLUMNS: ClassVar[dict] = {
        "india_compliance.patches.v15.multiple_pi_in_boe.execute": ("Bill of Entry", ["purchase_invoice"]),
        "india_compliance.patches.v15.make_e_invoice_log_extensible.execute": (
            "e-Invoice Log",
            ["sales_invoice"],
        ),
        "india_compliance.patches.v15.migrate_logo_for_printing.execute": (
            "Company",
            ["logo_for_printing"],
        ),
        "india_compliance.patches.v15.migrate_print_options_to_new_field.execute": (
            "Company Print Options",
            ["autofield", "autofield_value"],
        ),
        "india_compliance.patches.post_install.migrate_fields_for_gstr3b.execute": (
            "GSTR 3B Report",
            ["month", "company_address"],
        ),
        "india_compliance.patches.post_install.update_payment_entry_fields.execute": (
            "Payment Entry",
            ["customer_gstin"],
        ),
    }

    @contextmanager
    def legacy_columns(self, path):
        """Add back the columns `path` migrates, where the current schema no longer has them."""
        doctype, columns = self.LEGACY_COLUMNS.get(path, (None, []))
        added = [column for column in columns if not frappe.db.has_column(doctype, column)]

        for column in added:
            add_column(doctype, column, "Data")

        if added:
            frappe.clear_cache(doctype=doctype)

        try:
            yield
        finally:
            for column in added:
                frappe.db.sql_ddl(f"alter table `tab{doctype}` drop column `{column}`")

            if added:
                frappe.clear_cache(doctype=doctype)

    def test_every_patch_runs(self):
        failures = []

        frappe.db._disable_transaction_control += 1
        frappe.flags.in_patch = True

        try:
            for path in get_all_patch_paths():
                with self.legacy_columns(path):
                    frappe.db.savepoint("patch_smoke_test")
                    try:
                        frappe.get_attr(path)()
                    except Exception as e:
                        failures.append(f"{path}: {type(e).__name__}: {str(e)[:160]}")
                    finally:
                        frappe.db.rollback(save_point="patch_smoke_test")
        finally:
            frappe.db._disable_transaction_control -= 1
            frappe.flags.pop("in_patch", None)

        self.assertEqual(failures, [])


def get_all_patch_paths():
    patches = Path(frappe.get_app_path("india_compliance", "patches"))
    paths = []

    for file in sorted(patches.rglob("*.py")):
        if file.name == "__init__.py":
            continue

        module = ".".join(("india_compliance", "patches", *file.relative_to(patches).with_suffix("").parts))
        path = f"{module}.execute"

        try:
            frappe.get_attr(path)
        except AttributeError:
            continue  # a helper module rather than a patch

        paths.append(path)

    return paths


class TestPostInstallPatchQueries(IntegrationTestCase):
    def setUp(self):
        frappe.flags.in_patch = True
        self.addCleanup(frappe.flags.pop, "in_patch", None)

    def test_set_correct_state_number(self):
        from india_compliance.patches.post_install.setup_custom_fields_for_gst import execute

        addresses = {}
        for state_number in ("7", "24"):
            address = frappe.get_doc(
                {
                    "doctype": "Address",
                    "address_title": f"_Test Patch State {state_number}",
                    "address_type": "Billing",
                    "address_line1": "Test Address",
                    "city": "Test City",
                    "state": "Gujarat",
                    "country": "India",
                    "gst_state_number": state_number,
                }
            )
            address.flags.ignore_validate = True
            addresses[state_number] = address.insert(ignore_mandatory=True).name

        execute()

        self.assertEqual(frappe.db.get_value("Address", addresses["7"], "gst_state_number"), "07")
        self.assertEqual(frappe.db.get_value("Address", addresses["24"], "gst_state_number"), "24")

    def test_update_company_gstin_locks_the_field(self):
        """`allow_on_submit` is a Check column, and the patch writes it from a bool."""
        from india_compliance.patches.post_install.update_company_gstin import execute

        custom_field = frappe.db.get_value("Custom Field", {"fieldname": "company_gstin"}, "name")
        self.assertTrue(custom_field, "expected a company_gstin custom field to exist")

        frappe.db.set_value("Custom Field", custom_field, "allow_on_submit", 1)

        execute()

        self.assertEqual(frappe.db.get_value("Custom Field", custom_field, "allow_on_submit"), 0)

    @change_settings("GST Settings", {"enable_overseas_transactions": 1})
    def test_update_gst_treatment_for_import_transactions(self):
        from india_compliance.patches.post_install.update_gst_treatment_for_import_transactions import execute

        imported = create_purchase_invoice(
            supplier="_Test Foreign Supplier",
            supplier_gstin="",
            gst_category="Overseas",
            is_in_state=0,
        )
        domestic = create_purchase_invoice(is_in_state=1)

        self.assertIn(imported.itc_classification, ("Import Of Goods", "Import Of Service"))

        for invoice in (imported, domestic):
            frappe.db.set_value("Purchase Invoice Item", invoice.items[0].name, "gst_treatment", "Nil-Rated")

        execute()

        self.assertEqual(
            frappe.db.get_value("Purchase Invoice Item", imported.items[0].name, "gst_treatment"),
            "Taxable",
        )
        self.assertEqual(
            frappe.db.get_value("Purchase Invoice Item", domestic.items[0].name, "gst_treatment"),
            "Nil-Rated",
        )

    @change_settings("GST Settings", {"enable_overseas_transactions": 1})
    def test_update_reconciliation_status(self):
        from india_compliance.patches.post_install.update_reconciliation_status import execute

        not_applicable = create_purchase_invoice(
            supplier="_Test Foreign Supplier",
            supplier_gstin="",
            gst_category="Overseas",
            is_in_state=0,
        )
        unreconciled = create_purchase_invoice(is_in_state=1)

        for invoice in (not_applicable, unreconciled):
            frappe.db.set_value("Purchase Invoice", invoice.name, "reconciliation_status", "")

        execute()

        self.assertEqual(
            frappe.db.get_value("Purchase Invoice", not_applicable.name, "reconciliation_status"),
            "Not Applicable",
        )
        self.assertEqual(
            frappe.db.get_value("Purchase Invoice", unreconciled.name, "reconciliation_status"),
            "Unreconciled",
        )

    def test_update_e_waybill_status(self):
        """execute() only runs the status setters when some invoice still carries an e-Waybill,
        and cancelling one clears the number off the invoice -- so both states are needed."""
        from india_compliance.patches.post_install.update_e_waybill_status import execute

        generated = create_sales_invoice(is_in_state=1)
        frappe.db.set_value(
            "Sales Invoice", generated.name, {"e_waybill_status": "", "ewaybill": "123456789012"}
        )

        cancelled = create_sales_invoice(is_in_state=1)
        frappe.db.set_value("Sales Invoice", cancelled.name, {"e_waybill_status": "", "ewaybill": ""})
        frappe.get_doc(
            {
                "doctype": "e-Waybill Log",
                "e_waybill_number": "123456789013",
                "reference_doctype": "Sales Invoice",
                "reference_name": cancelled.name,
                "is_cancelled": 1,
            }
        ).insert(ignore_mandatory=True)

        execute()

        self.assertEqual(
            frappe.db.get_value("Sales Invoice", generated.name, "e_waybill_status"), "Generated"
        )
        self.assertEqual(
            frappe.db.get_value("Sales Invoice", cancelled.name, "e_waybill_status"), "Cancelled"
        )

    @change_settings("GST Settings", {"enable_overseas_transactions": 1})
    def test_set_pending_boe_qty(self):
        from india_compliance.patches.v14.set_pending_boe_qty import execute

        consumed, ordered = 4, 10
        invoice = create_purchase_invoice(
            supplier="_Test Foreign Supplier",
            supplier_gstin="",
            gst_category="Overseas",
            is_in_state=0,
            qty=ordered,
        )

        boe = make_bill_of_entry(invoice.name)
        boe.items[0].qty = consumed
        boe.update(
            {
                "bill_of_entry_no": "PATCH-BOE",
                "bill_of_entry_date": frappe.utils.today(),
                "posting_date": frappe.utils.today(),
            }
        )
        boe.save(ignore_permissions=True).submit()

        pi_item = invoice.items[0].name
        self.assertEqual(
            frappe.db.get_value("Purchase Invoice Item", pi_item, "pending_boe_qty"),
            ordered - consumed,
            "submitting the Bill of Entry should already have reduced the pending quantity",
        )

        frappe.db.set_value("Purchase Invoice Item", pi_item, "pending_boe_qty", 0)

        execute()

        self.assertEqual(
            frappe.db.get_value("Purchase Invoice Item", pi_item, "pending_boe_qty"),
            ordered - consumed,
        )

    @change_settings("GST Settings", {"enable_overseas_transactions": 1})
    def test_set_pending_boe_qty_without_any_bill_of_entry(self):
        from india_compliance.patches.v14.set_pending_boe_qty import execute

        invoice = create_purchase_invoice(
            supplier="_Test Foreign Supplier",
            supplier_gstin="",
            gst_category="Overseas",
            is_in_state=0,
            qty=10,
        )
        frappe.db.set_value("Purchase Invoice Item", invoice.items[0].name, "pending_boe_qty", 0)

        execute()

        self.assertEqual(
            frappe.db.get_value("Purchase Invoice Item", invoice.items[0].name, "pending_boe_qty"),
            10,
        )
