from email.utils import formatdate

import frappe
from frappe import _
from frappe.utils import format_date, getdate

from india_compliance.gst_india.constants import EXPORT_TYPES, GST_CATEGORIES
from india_compliance.gst_india.utils.e_waybill import validate_company
from india_compliance.gst_india.utils.invoice_data import GSTInvoiceData


def _generate_e_invoice():
    pass


def validate_e_invoice_applicability(doc, gst_settings=None, throw=True):
    if doc.gst_category == "Unregistered":
        if throw:
            frappe.throw(
                _(
                    "e-Invoice is not applicable for invoices with Unregistered"
                    " Customers"
                )
            )

        return

    if not gst_settings:
        gst_settings = frappe.get_cached_doc("GST Settings")

    if not gst_settings.enable_api:
        if throw:
            frappe.throw(_("Enable API in GST Settings to generate e-Invoice"))

        return

    if not gst_settings.enable_e_invoice:
        if throw:
            frappe.throw(_("Enable e-Invoicing in GST Settings to generate e-Invoice"))

        return

    if getdate(gst_settings.e_invoice_applicable_from) > getdate(doc.posting_date):
        if throw:
            frappe.throw(
                _(
                    "e-Invoice is not applicable for invoices before {0} as per your"
                    " GST Settings"
                ).format(format_date(gst_settings.e_invoice_applicable_from))
            )

        return

    return True


class EInvoiceData(GSTInvoiceData):
    def __init__(self, doc, json_download=False, sandbox=False):
        super().__init__(doc, json_download, sandbox)

    def get_e_invoice_data(self):
        pass

    def pre_validate_invoice(self):
        super().pre_validate_invoice()
        self.check_e_invoice_applicability()

    def check_e_invoice_applicability(self):
        self.validate_company()
        self.validate_non_gst_items()
        validate_e_invoice_applicability(self.doc, self.settings)

    def update_item_details(self, row):
        super().update_item_details(row)

        self.item_details.update(
            {
                "discount_amount": 0,
                "serial_no": "",
                "is_service_item": "Y" if row.gst_hsn_code.startswith("99") else "N",
                "unit_rate": abs(row.taxable_value / row.qty)
                if row.qty
                else abs(row.taxable_value),
            }
        )

        if row.get("batch_no"):
            batch_expiry_date = frappe.db.get_value(
                "Batch", row.batch_no, "expiry_date"
            )
            batch_expiry_date = format_date(batch_expiry_date, self.DATE_FORMAT)
            self.item_details.update(
                {
                    "batch_number": row.batch_no,
                    "batch_expiry_date": batch_expiry_date,
                }
            )

    def update_invoice_details(self):
        super().update_invoice_details()

        self.invoice_details.update(
            {
                "tax_scheme": "GST",
                "supply_type": self.get_supply_type(),
                "reverse_charge": self.doc.reverse_charge,
                "invoice_type": "CRN" if self.doc.is_return else "INV",
            }
        )

        # PAYMENT DETAILS
        # cover cases where advance payment is made
        if self.doc.is_pos and self.doc.base_paid_amount:
            self.invoice_details.update(
                {
                    "payee_name": self.doc.company,
                    "mode_of_payment": ", ".join(
                        [d.mode_of_payment for d in self.doc.payments]
                    ),
                    "paid_amount": self.doc.base_paid_amount,
                    "outstanding_amount": self.doc.outstanding_amount,
                }
            )

        # RETURN/CN DETIALS
        if self.doc.is_return and (return_against := self.doc.return_against):
            self.invoice_details.update(
                {
                    "original_invoice_number": return_against,
                    "original_invoice_date": format_date(
                        frappe.db.get_value(
                            "Sales Invoice", return_against, "posting_date"
                        ),
                        self.DATE_FORMAT,
                    ),
                }
            )

    def get_supply_type(self):
        supply_type = GST_CATEGORIES[self.doc.gst_category]
        if self.doc.gst_category in ("Overseas", "SEZ"):
            export_type = EXPORT_TYPES[self.doc.export_type]
            supply_type = f"{supply_type}{export_type}"

        return supply_type
