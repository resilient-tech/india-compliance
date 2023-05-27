import frappe
from frappe import _

from india_compliance.gst_india.constants import GST_INVOICE_NUMBER_FORMAT
from india_compliance.gst_india.overrides.transaction import (
    ignore_gst_validations,
    validate_mandatory_fields,
    validate_transaction,
)
from india_compliance.gst_india.utils import is_api_enabled
from india_compliance.gst_india.utils.e_invoice import validate_e_invoice_applicability
from india_compliance.gst_india.utils.transaction_data import (
    validate_unique_hsn_and_uom,
)


def onload(doc, method=None):
    if not doc.get("ewaybill"):
        if doc.gst_category == "Overseas" and is_e_waybill_applicable(doc):
            doc.set_onload(
                "shipping_address_in_india", is_shipping_address_in_india(doc)
            )

        if not doc.get("irn"):
            return

    gst_settings = frappe.get_cached_value(
        "GST Settings",
        "GST Settings",
        ("enable_api", "enable_e_waybill", "enable_e_invoice", "api_secret"),
        as_dict=1,
    )

    if not is_api_enabled(gst_settings):
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
    validate_fields_and_set_status_for_e_invoice(doc)
    validate_unique_hsn_and_uom(doc)
    validate_port_address(doc)


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

    validate_mandatory_fields(
        doc,
        "customer_address",
        _("{0} is a mandatory field for generating e-Invoices"),
    )

    if doc._action == "submit" and not doc.irn:
        doc.einvoice_status = "Pending"


def validate_port_address(doc):
    if (
        doc.gst_category != "Overseas"
        or not is_e_waybill_applicable(doc)
        or doc.port_address
        or is_shipping_address_in_india(doc)
    ):
        return

    label = doc.meta.get_label("port_address")

    frappe.msgprint(
        _(
            "{0} must be specified for generating e-Waybills against export of goods"
            " (if Shipping Address is not in India)"
        ).format(frappe.bold(label)),
        title=_("{0} Not Set").format(label),
        indicator="yellow",
    )


def is_shipping_address_in_india(doc):
    if doc.shipping_address_name and (
        frappe.db.get_value("Address", doc.shipping_address_name, "country") == "India"
    ):
        return True


def on_submit(doc, method=None):
    if getattr(doc, "_submitted_from_ui", None) or not doc.company_gstin:
        return

    gst_settings = frappe.get_cached_doc("GST Settings")
    if not is_api_enabled(gst_settings):
        return

    if (
        validate_e_invoice_applicability(doc, gst_settings, throw=False)
        and gst_settings.auto_generate_e_invoice
    ):
        frappe.enqueue(
            "india_compliance.gst_india.utils.e_invoice.generate_e_invoice",
            enqueue_after_commit=True,
            queue="short",
            docname=doc.name,
            throw=False,
        )

        return

    if gst_settings.auto_generate_e_waybill and is_e_waybill_applicable(
        doc, gst_settings
    ):
        frappe.enqueue(
            "india_compliance.gst_india.utils.e_waybill.generate_e_waybill",
            enqueue_after_commit=True,
            queue="short",
            doctype=doc.doctype,
            docname=doc.name,
        )


def is_e_waybill_applicable(doc, gst_settings=None):
    if not gst_settings:
        gst_settings = frappe.get_cached_doc("GST Settings")

    return bool(
        gst_settings.enable_e_waybill
        and doc.company_gstin != doc.billing_address_gstin
        and not doc.ewaybill
        and not doc.is_return
        and not doc.is_debit_note
        and abs(doc.base_grand_total) >= gst_settings.e_waybill_threshold
        and any(
            item
            for item in doc.items
            if item.gst_hsn_code
            and not item.gst_hsn_code.startswith("99")
            and item.qty != 0
        )
    )


def on_update_after_submit(doc, method=None):
    if not doc.has_value_changed("group_same_items") or ignore_gst_validations(doc):
        return

    if doc.ewaybill or doc.irn:
        frappe.msgprint(
            _(
                "You have already generated e-Waybill/e-Invoice for this document. This could result in mismatch of item details in e-Waybill/e-Invoice with print format.",
            ),
            title="Possible Inconsistent Item Details",
            indicator="orange",
        )


def get_dashboard_data(data):
    return update_dashboard_with_gst_logs(
        "Sales Invoice", data, "e-Waybill Log", "e-Invoice Log", "Integration Request"
    )


def update_dashboard_with_gst_logs(doctype, data, *log_doctypes):
    if not is_api_enabled():
        return data

    data.setdefault("non_standard_fieldnames", {}).update(
        {
            "e-Waybill Log": "reference_name",
            "Integration Request": "reference_docname",
        }
    )

    data.setdefault("dynamic_links", {}).update(
        reference_docname=[doctype, "reference_doctype"],
        reference_name=[doctype, "reference_doctype"],
    )

    transactions = data.setdefault("transactions", [])

    # GST Logs section looks best at the 3rd position
    # If there are less than 2 transactions, insert will be equivalent to append
    transactions.insert(2, {"label": _("GST Logs"), "items": log_doctypes})

    return data
