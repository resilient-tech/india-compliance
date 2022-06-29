import frappe
from frappe import _, bold
from frappe.model import delete_doc

from india_compliance.gst_india.constants import GST_INVOICE_NUMBER_FORMAT
from india_compliance.gst_india.overrides.transaction import (
    validate_mandatory_fields,
    validate_transaction,
)
from india_compliance.gst_india.utils.e_invoice import validate_e_invoice_applicability


def onload(doc, method=None):
    if not doc.get("ewaybill") and not doc.get("irn"):
        return

    gst_settings = frappe.get_cached_value(
        "GST Settings",
        "GST Settings",
        ("enable_api", "enable_e_waybill", "enable_e_invoice"),
        as_dict=1,
    )

    if not gst_settings.enable_api:
        return

    if gst_settings.enable_e_waybill and doc.ewaybill:
        doc.set_onload(
            "e_waybill_info",
            frappe.get_value(
                "e-Waybill Log",
                doc.ewaybill,
                ("created_on", "valid_upto"),
                as_dict=True,
            ),
        )

    if gst_settings.enable_e_invoice and doc.irn:
        doc.set_onload(
            "e_invoice_info",
            frappe.get_value(
                "e-Invoice Log",
                doc.irn,
                "acknowledged_on",
                as_dict=True,
            ),
        )


def validate(doc, method=None):
    if validate_transaction(doc) is False:
        return

    validate_invoice_number(doc)
    validate_mandatory_fields(doc, ("place_of_supply", "gst_category"))
    validate_fields_and_set_status_for_e_invoice(doc)
    validate_billing_address_gstin(doc)


def validate_invoice_number(doc):
    """Validate GST invoice number requirements."""

    if len(doc.name) > 16:
        frappe.throw(
            _("GST Invoice Number cannot exceed 16 characters"),
            title=_("Invalid GST Invoice Number"),
        )

    if not GST_INVOICE_NUMBER_FORMAT.match(doc.name):
        frappe.throw(
            _(
                "GST Invoice Number should start with an alphanumeric character and can"
                " only contain alphanumeric characters, dash (-) and slash (/)"
            ),
            title=_("Invalid GST Invoice Number"),
        )


def validate_fields_and_set_status_for_e_invoice(doc):
    gst_settings = frappe.get_cached_doc("GST Settings")
    if not gst_settings.enable_e_invoice or not validate_e_invoice_applicability(
        doc, gst_settings=gst_settings, throw=False
    ):
        return

    for field in ("customer_address",):
        if not doc.get(field):
            frappe.throw(
                _("{0} is a mandatory field for generating e-Invoices").format(
                    bold(_(doc.meta.get_label(field))),
                )
            )

    if doc._action == "submit" and not doc.irn:
        doc.einvoice_status = "Pending"


def validate_billing_address_gstin(doc):
    if doc.company_gstin == doc.billing_address_gstin:
        frappe.throw(
            _("Billing Address GSTIN and Company GSTIN cannot be the same"),
            title=_("Invalid Billing Address GSTIN"),
        )


def ignore_logs_on_trash(doc, method=None):
    # TODO: design better way to achieve this
    delete_doc.doctypes_to_skip += (
        "e-Waybill Log",
        "e-Invoice Log",
        "Integration Request",
    )
