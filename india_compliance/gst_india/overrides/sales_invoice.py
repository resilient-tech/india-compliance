import frappe
from frappe import _, bold
from frappe.model import delete_doc

from india_compliance.gst_india.constants import GST_INVOICE_NUMBER_FORMAT
from india_compliance.gst_india.overrides.invoice import update_taxable_values
from india_compliance.gst_india.overrides.transaction import (
    is_indian_registered_company,
    set_place_of_supply,
    validate_gst_accounts,
    validate_hsn_code,
    validate_items,
    validate_mandatory_fields,
    validate_overseas_gst_category,
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
    if not is_indian_registered_company(doc):
        return

    if validate_items(doc) is False:
        # If there are no GST items, then no need to proceed further
        return

    set_place_of_supply(doc)
    update_taxable_values(doc)
    validate_invoice_number(doc)
    validate_mandatory_fields(doc, ("company_gstin", "place_of_supply", "gst_category"))
    validate_gst_accounts(doc)
    validate_fields_and_set_status_for_e_invoice(doc)
    validate_billing_address_gstin(doc)
    validate_hsn_code(doc)
    validate_overseas_gst_category(doc)


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
            _(
                "Billing Address GSTIN and Company GSTIN cannot be same. Please"
                " change the Billing Address"
            ),
            title=_("Invalid Billing Address GSTIN"),
        )


def ignore_logs_on_trash(doc, method=None):
    # TODO: design better way to achieve this
    delete_doc.doctypes_to_skip += (
        "e-Waybill Log",
        "e-Invoice Log",
        "Integration Request",
    )
