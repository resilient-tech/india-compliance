import frappe
from frappe import _, bold
from frappe.model import delete_doc

from india_compliance.gst_india.constants import GST_INVOICE_NUMBER_FORMAT
from india_compliance.gst_india.utils import (
    get_all_gst_accounts,
    get_gst_accounts_by_type,
)
from india_compliance.gst_india.utils.e_invoice import validate_e_invoice_applicability


def onload(doc, method=None):
    if not doc.ewaybill and not doc.irn:
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


def validate_gst_invoice(doc, method=None):
    country, gst_category = frappe.get_cached_value(
        "Company", doc.company, ("country", "gst_category")
    )

    if country != "India" or gst_category == "Unregistered":
        return

    if validate_items(doc) is False:
        # If there are no GST items, then no need to proceed further
        return

    validate_invoice_number(doc)
    validate_mandatory_fields(doc)
    validate_gst_accounts(doc)
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


def validate_mandatory_fields(doc):
    for field in ("company_gstin", "place_of_supply", "gst_category"):
        if not doc.get(field):
            frappe.throw(
                _(
                    "{0} is a mandatory field for creating a GST Compliant Invoice"
                ).format(
                    bold(_(doc.meta.get_label(field))),
                )
            )


def validate_fields_and_set_status_for_e_invoice(doc):
    if not validate_e_invoice_applicability(doc, throw=False):
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


def validate_items(doc):
    """Validate Items for a GST Compliant Invoice"""

    if not doc.items:
        return

    item_tax_templates = frappe._dict()
    items_with_duplicate_taxes = []
    non_gst_items = []
    has_gst_items = False

    for row in doc.items:
        # Collect data to validate that non-GST items are not used with GST items
        if row.is_non_gst:
            non_gst_items.append(row.idx)
            continue

        has_gst_items = True

        # Different Item Tax Templates should not be used for the same Item Code
        if row.item_code not in item_tax_templates:
            item_tax_templates[row.item_code] = row.item_tax_template
            continue

        if row.item_tax_template != item_tax_templates[row.item_code]:
            items_with_duplicate_taxes.append(bold(row.item_code))

    if not has_gst_items:
        return False

    if non_gst_items:
        frappe.throw(
            _(
                "Items not covered under GST cannot be clubbed with items for which GST"
                " is applicable. Please create another invoice for items in the"
                " following row numbers:<br>{0}"
            ).format(", ".join(bold(row_no) for row_no in non_gst_items)),
            title=_("Invalid Items"),
        )

    if items_with_duplicate_taxes:
        frappe.throw(
            _(
                "Cannot use different Item Tax Templates in different rows for"
                " following items:<br> {0}"
            ).format("<br>".join(items_with_duplicate_taxes)),
            title="Inconsistent Item Tax Templates",
        )


def validate_billing_address_gstin(doc):
    if doc.company_gstin == doc.billing_address_gstin:
        frappe.throw(
            _(
                "Billing Address GSTIN and Company GSTIN cannot be same. Please"
                " change the Billing Address"
            ),
            title=_("Invalid Billing Address GSTIN"),
        )


def validate_gst_accounts(doc):
    """
    Validate GST accounts before invoice creation
    - Only Output Accounts should be allowed in GST Sales Invoice
    - If supply made to SEZ/Overseas without payment of tax, then no GST account should be specified
    - SEZ supplies should not have CGST or SGST account
    - Inter-State supplies should not have CGST or SGST account
    - Intra-State supplies should not have IGST account
    """

    if not doc.taxes:
        return

    accounts_list = get_all_gst_accounts(doc.company)
    output_accounts = get_gst_accounts_by_type(doc.company, "Output")

    for row in doc.taxes:
        account_head = row.account_head

        if account_head not in accounts_list or not row.tax_amount:
            continue

        if (
            doc.gst_category in ("SEZ", "Overseas")
            and doc.export_type == "Without Payment of Tax"
        ):
            frappe.throw(
                _(
                    "Cannot charge GST in Row #{0} since Export Type is set to Without"
                    " Payment of Tax"
                ).format(row.idx)
            )

        if account_head not in output_accounts.values():
            frappe.throw(
                _(
                    "{0} is not an Output GST Account and cannot be used in Sales"
                    " Transactions."
                ).format(bold(account_head))
            )

        # Inter State supplies should not have CGST or SGST account
        if (
            doc.place_of_supply[:2] != doc.company_gstin[:2]
            or doc.gst_category == "SEZ"
        ):
            if account_head in (
                output_accounts.cgst_account,
                output_accounts.sgst_account,
            ):
                frappe.throw(
                    _(
                        "Row #{0}: Cannot charge CGST/SGST for inter-state supplies"
                    ).format(row.idx)
                )

        # Intra State supplies should not have IGST account
        elif account_head == output_accounts.igst_account:
            frappe.throw(
                _("Row #{0}: Cannot charge IGST for intra-state supplies").format(
                    row.idx
                )
            )


def ignore_logs_on_trash(doc, method=None):
    # TODO: design better way to achieve this
    delete_doc.doctypes_to_skip += (
        "e-Waybill Log",
        "e-Invoice Log",
        "Integration Request",
    )
