import frappe
from frappe.tests import IntegrationTestCase
from frappe.tests.utils import change_settings

from india_compliance.gst_india.utils import validate_invoice_number
from india_compliance.gst_india.utils.tests import append_item, create_transaction


class TestSalesInvoice(IntegrationTestCase):
    def test_validate_invoice_number(self):
        posting_date = "2021-05-01"

        invalid_names = [
            "SI$1231",
            "012345678901234567",
            "SI 2020 05",
            "SI.2020.0001",
            "PI2021 - 001",
        ]
        for name in invalid_names:
            doc = frappe._dict(name=name, posting_date=posting_date, doctype="Sales Invoice")
            self.assertRaises(frappe.ValidationError, validate_invoice_number, doc)

        valid_names = [
            "012345678901236",
            "SI/2020/0001",
            "SI/2020-0001",
            "2020-PI-0001",
            "PI2020-0001",
        ]
        for name in valid_names:
            doc = frappe._dict(name=name, posting_date=posting_date)
            try:
                validate_invoice_number(doc)
            except frappe.ValidationError:
                self.fail(f"Valid name {name} throwing error")

    @change_settings("GST Settings", {"enable_overseas_transactions": 1, "round_off_gst_values": 1})
    @change_settings(
        "Accounts Settings",
        {"allow_multi_currency_invoices_against_single_party_account": 1},
    )
    def test_item_gst_amount_in_multicurrency_invoice(self):
        """
        In a multicurrency invoice, ERPNext rounds the doc-level tax in
        transaction currency before converting to base currency. So the
        doc-level `base_tax_amount_after_discount_amount` diverges from
        per-item `rate% x base_net_amount`.

        India Compliance concentrates that residual onto the last taxable
        item so the sum of per-item gst amounts matches the doc total.
        """
        doc = create_transaction(
            doctype="Sales Invoice",
            customer="_Test Foreign Customer",
            customer_address="_Test Foreign Customer-Billing",
            is_export_with_gst=1,
            currency="USD",
            conversion_rate=95.99,
            rate=5932.20,
            qty=9,
            is_out_state=True,
            do_not_save=True,
        )
        append_item(doc, frappe._dict(rate=1234.56, qty=3))
        doc.insert()

        item_a = doc.items[0]
        item_b = doc.items[1]

        self.assertEqual(item_a.igst_rate, 18)
        self.assertEqual(item_b.igst_rate, 18)

        igst_row = next(t for t in doc.taxes if t.gst_tax_type == "igst")
        self.assertEqual(
            item_a.igst_amount + item_b.igst_amount, igst_row.base_tax_amount_after_discount_amount
        )
