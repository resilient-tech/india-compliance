import frappe
from frappe import _, bold
from frappe.utils import flt, fmt_money

from india_compliance.gst_india.overrides.payment_entry import get_taxes_summary
from india_compliance.gst_india.overrides.transaction import (
    ignore_gst_validations,
    validate_mandatory_fields,
    validate_transaction,
)
from india_compliance.gst_india.overrides.unreconcile_payment import (
    reverse_gst_adjusted_against_payment_entry,
)
from india_compliance.gst_india.utils import (
    are_goods_supplied,
    get_validated_country_code,
    is_api_enabled,
    is_foreign_doc,
    validate_invoice_number,
)
from india_compliance.gst_india.utils.e_invoice import (
    get_e_invoice_info,
    validate_e_invoice_applicability,
    validate_hsn_codes_for_e_invoice,
)
from india_compliance.gst_india.utils.e_waybill import get_e_waybill_info
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

    gst_settings = frappe.get_cached_doc("GST Settings")

    if not is_api_enabled(gst_settings):
        return

    if gst_settings.enable_e_waybill and doc.ewaybill:
        doc.set_onload("e_waybill_info", get_e_waybill_info(doc))

    if gst_settings.enable_e_invoice and doc.irn:
        doc.set_onload("e_invoice_info", get_e_invoice_info(doc))


def validate(doc, method=None):
    if validate_transaction(doc) is False:
        return

    gst_settings = frappe.get_cached_doc("GST Settings")

    validate_invoice_number(doc)
    validate_credit_debit_note(doc)
    validate_fields_and_set_status_for_e_invoice(doc, gst_settings)
    validate_unique_hsn_and_uom(doc)
    validate_port_address(doc)
    set_and_validate_advances_with_gst(doc)
    set_e_waybill_status(doc, gst_settings)


def validate_credit_debit_note(doc):
    if doc.is_return and doc.is_debit_note:
        frappe.throw(
            _(
                "You have selected both 'Is Return' and 'Is Rate Adjustment Entry'. You can select only one of them."
            ),
            title=_("Invalid Options Selected"),
        )


def validate_fields_and_set_status_for_e_invoice(doc, gst_settings):
    if not gst_settings.enable_e_invoice or not validate_e_invoice_applicability(
        doc, gst_settings=gst_settings, throw=False
    ):
        doc.einvoice_status = "Not Applicable"
        return

    validate_mandatory_fields(
        doc,
        "customer_address",
        _("{0} is a mandatory field for generating e-Invoices"),
    )

    validate_hsn_codes_for_e_invoice(doc)

    if is_foreign_doc(doc):
        country = frappe.db.get_value("Address", doc.customer_address, "country")
        get_validated_country_code(country)

    if doc.docstatus == 1 and not doc.irn:
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
    if getattr(doc, "_submitted_from_ui", None) or validate_transaction(doc) is False:
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

    if (
        gst_settings.auto_generate_e_waybill
        and is_e_waybill_applicable(doc, gst_settings)
        and not doc.is_debit_note
        and not doc.is_return
    ):
        frappe.enqueue(
            "india_compliance.gst_india.utils.e_waybill.generate_e_waybill",
            enqueue_after_commit=True,
            queue="short",
            doctype=doc.doctype,
            docname=doc.name,
        )


def before_cancel(doc, method=None):
    payment_references = frappe.get_all(
        "Payment Entry Reference",
        filters={
            "reference_doctype": doc.doctype,
            "reference_name": doc.name,
            "docstatus": 1,
        },
        fields=["name as voucher_detail_no", "parent as payment_name"],
    )

    if not payment_references:
        return

    for reference in payment_references:
        reverse_gst_adjusted_against_payment_entry(
            reference.voucher_detail_no, reference.payment_name
        )


def is_e_waybill_applicable(doc, gst_settings=None):
    if not gst_settings:
        gst_settings = frappe.get_cached_doc("GST Settings")

    return bool(
        gst_settings.enable_e_waybill
        and doc.company_gstin != doc.billing_address_gstin
        and not doc.ewaybill
        and abs(doc.base_grand_total) >= gst_settings.e_waybill_threshold
        and are_goods_supplied(doc)
    )


def on_update_after_submit(doc, method=None):
    if not doc.has_value_changed("group_same_items") or ignore_gst_validations(doc):
        return

    if doc.ewaybill or doc.irn:
        frappe.msgprint(
            _(
                "You have already generated e-Waybill/e-Invoice for this document."
                " This could result in mismatch of item details in e-Waybill/e-Invoice with print format.",
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
            "GST Inward Supply": "link_name",
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


def set_e_waybill_status(doc, gst_settings=None):
    if doc.docstatus != 1 or doc.e_waybill_status:
        return

    e_waybill_status = "Not Applicable"

    if is_e_waybill_applicable(doc, gst_settings):
        e_waybill_status = "Pending"

    if doc.ewaybill:
        e_waybill_status = "Manually Generated"

    doc.update({"e_waybill_status": e_waybill_status})


def set_and_validate_advances_with_gst(doc):
    if not doc.advances:
        return

    taxes = get_taxes_summary(doc.company, doc.advances)

    allocated_amount_with_taxes = 0
    tax_amount = 0

    for advance in doc.get("advances"):
        if not advance.allocated_amount:
            continue

        tax_row = taxes.get(
            advance.reference_name, frappe._dict(paid_amount=1, tax_amount=0)
        )

        _tax_amount = flt(
            advance.allocated_amount / tax_row.paid_amount * tax_row.tax_amount, 2
        )
        tax_amount += _tax_amount
        allocated_amount_with_taxes += _tax_amount
        allocated_amount_with_taxes += advance.allocated_amount

    excess_allocation = flt(
        flt(allocated_amount_with_taxes, 2) - (doc.rounded_total or doc.grand_total), 2
    )
    if excess_allocation > 0:
        message = _(
            "Allocated amount with taxes (GST) in advances table cannot be greater than"
            " outstanding amount of the document. Allocated amount with taxes is greater by {0}."
        ).format(bold(fmt_money(excess_allocation, currency=doc.currency)))

        if excess_allocation < 1:
            message += "<br><br>Is it becasue of Rounding Adjustment? Try disabling Rounded Total in the document."

        frappe.throw(message, title=_("Invalid Allocated Amount"))

    doc.total_advance = allocated_amount_with_taxes
    doc.set_payment_schedule()
    doc.outstanding_amount -= tax_amount
    frappe.flags.gst_excess_allocation_validated = True
