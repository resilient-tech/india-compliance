import frappe
from frappe.utils import cint, flt

from ..utils import get_gst_accounts


def update_taxable_values(doc, method=None):
    country = frappe.get_cached_value("Company", doc.company, "country")

    if country != "India":
        return

    gst_accounts = get_gst_accounts(doc.company)

    # Only considering sgst account to avoid inflating taxable value
    gst_account_list = (
        gst_accounts.get("sgst_account", [])
        + gst_accounts.get("sgst_account", [])
        + gst_accounts.get("igst_account", [])
    )

    additional_taxes = 0
    total_charges = 0
    item_count = 0
    considered_rows = []

    for tax in doc.get("taxes"):
        prev_row_id = cint(tax.row_id) - 1
        if tax.account_head in gst_account_list and prev_row_id not in considered_rows:
            if tax.charge_type == "On Previous Row Amount":
                additional_taxes += doc.get("taxes")[
                    prev_row_id
                ].tax_amount_after_discount_amount
                considered_rows.append(prev_row_id)
            if tax.charge_type == "On Previous Row Total":
                additional_taxes += (
                    doc.get("taxes")[prev_row_id].base_total - doc.base_net_total
                )
                considered_rows.append(prev_row_id)

    for item in doc.get("items"):
        proportionate_value = item.base_net_amount if doc.base_net_total else item.qty
        total_value = doc.base_net_total if doc.base_net_total else doc.total_qty

        applicable_charges = flt(
            flt(
                proportionate_value * (flt(additional_taxes) / flt(total_value)),
                item.precision("taxable_value"),
            )
        )
        item.taxable_value = applicable_charges + proportionate_value
        total_charges += applicable_charges
        item_count += 1

    if total_charges != additional_taxes:
        diff = additional_taxes - total_charges
        doc.get("items")[item_count - 1].taxable_value += diff
