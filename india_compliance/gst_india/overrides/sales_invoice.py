import re

import frappe
from frappe import _
from frappe.utils import getdate

from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice

from india_compliance.gst_india.utils.e_waybill import EWaybillData

GST_INVOICE_NUMBER_FORMAT = re.compile(r"^[a-zA-Z0-9\-/]+$")  # alphanumeric and - /


def validate_document_name(doc, method=None):
    """Validate GST invoice number requirements."""

    country = frappe.get_cached_value("Company", doc.company, "country")

    # Date was chosen as start of next FY to avoid irritating current users.
    if country != "India" or getdate(doc.posting_date) < getdate("2021-04-01"):
        return

    if len(doc.name) > 16:
        frappe.throw(
            _(
                "Maximum length of document number should be 16 characters as per GST rules. Please change the naming series."
            )
        )

    if not GST_INVOICE_NUMBER_FORMAT.match(doc.name):
        frappe.throw(
            _(
                "Document name should only contain alphanumeric values, dash(-) and slash(/) characters as per GST rules. Please change the naming series."
            )
        )


# TODO: naming
class CustomSalesInvoice(SalesInvoice, EWaybillData):
    pass
