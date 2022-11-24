import frappe
from frappe import _, bold

from india_compliance.gst_india.constants import GST_INVOICE_NUMBER_FORMAT
from india_compliance.gst_india.overrides.transaction import validate_transaction
from india_compliance.gst_india.utils import is_api_enabled
from india_compliance.gst_india.utils.e_invoice import validate_e_invoice_applicability


def onload(doc, method=None):
    if not doc.get("ewaybill") and not doc.get("irn"):
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

    elif (
        not gst_settings.enable_e_waybill
        or not gst_settings.auto_generate_e_waybill
        or doc.ewaybill
        or doc.is_return
        or doc.is_debit_note
        or abs(doc.base_grand_total) < gst_settings.e_waybill_threshold
        or not any(
            item
            for item in doc.items
            if item.gst_hsn_code
            and not item.gst_hsn_code.startswith("99")
            and item.qty != 0
        )
    ):
        return

    frappe.enqueue(
        "india_compliance.gst_india.utils.e_waybill.generate_e_waybill",
        enqueue_after_commit=True,
        queue="short",
        doctype=doc.doctype,
        docname=doc.name,
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
