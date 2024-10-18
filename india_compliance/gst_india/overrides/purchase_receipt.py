import frappe
from frappe import _

from india_compliance.gst_india.overrides.purchase_invoice import (
    set_ineligibility_reason,
)
from india_compliance.gst_india.overrides.sales_invoice import (
    update_dashboard_with_gst_logs,
)
from india_compliance.gst_india.overrides.transaction import (
    get_taxes_and_charges,
    ignore_gst_validations,
    validate_mandatory_fields,
    validate_transaction,
)


def get_dashboard_data(data):
    return update_dashboard_with_gst_logs(
        "Purchase Receipt",
        data,
        "e-Waybill Log",
        "Integration Request",
    )


def after_mapping(doc, method, source_doc):
    if not source_doc.doctype == "Subcontracting Receipt":
        return

    if not source_doc.items:
        frappe.throw(
            _(
                "Purchase Order Item reference is missing in Subcontracting Receipt {0}"
            ).format(source_doc.name)
        )

    po_name = source_doc.items[0].purchase_order
    po_taxes_and_charges = frappe.db.get_value(
        "Purchase Order", po_name, fieldname="taxes_and_charges"
    )

    doc.taxes_and_charges = po_taxes_and_charges
    taxes = get_taxes_and_charges(
        "Purchase Taxes and Charges Template", po_taxes_and_charges
    )

    for tax_row in taxes:
        doc.append("taxes", tax_row)


def onload(doc, method=None):
    if ignore_gst_validations(doc):
        return

    if (
        validate_mandatory_fields(
            doc, ("company_gstin", "place_of_supply", "gst_category"), throw=False
        )
        is False
    ):
        return

    set_ineligibility_reason(doc, show_alert=False)


def validate(doc, method=None):
    if validate_transaction(doc) is False:
        return

    set_ineligibility_reason(doc)
