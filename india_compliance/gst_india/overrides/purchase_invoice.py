import frappe
from frappe import _
from frappe.utils import flt

from india_compliance.gst_india.utils import get_gst_accounts


def validate_reverse_charge_transaction(doc, method):
    country = frappe.get_cached_value("Company", doc.company, "country")

    if country != "India":
        return

    base_gst_tax = 0
    base_reverse_charge_booked = 0

    if doc.is_reverse_charge:
        gst_accounts = get_gst_accounts(doc.company, only_reverse_charge=1)
        reverse_charge_accounts = (
            gst_accounts.get("cgst_account")
            + gst_accounts.get("sgst_account")
            + gst_accounts.get("igst_account")
        )

        gst_accounts = get_gst_accounts(doc.company, only_non_reverse_charge=1)
        non_reverse_charge_accounts = (
            gst_accounts.get("cgst_account")
            + gst_accounts.get("sgst_account")
            + gst_accounts.get("igst_account")
        )

        for tax in doc.get("taxes"):
            if tax.account_head in non_reverse_charge_accounts:
                if tax.add_deduct_tax == "Add":
                    base_gst_tax += tax.base_tax_amount_after_discount_amount
                else:
                    base_gst_tax += tax.base_tax_amount_after_discount_amount
            elif tax.account_head in reverse_charge_accounts:
                if tax.add_deduct_tax == "Add":
                    base_reverse_charge_booked += (
                        tax.base_tax_amount_after_discount_amount
                    )
                else:
                    base_reverse_charge_booked += (
                        tax.base_tax_amount_after_discount_amount
                    )

        if base_gst_tax != base_reverse_charge_booked:
            msg = _("Booked reverse charge is not equal to applied tax amount")
            msg += "<br>"
            msg += _(
                "Please refer {gst_document_link} to learn more about how to setup and create reverse charge invoice"
            ).format(
                gst_document_link='<a href="https://docs.erpnext.com/docs/user/manual/en/regional/india/gst-setup">GST Documentation</a>'
            )

            frappe.throw(msg)


def update_itc_availed_fields(doc, method):
    country = frappe.get_cached_value("Company", doc.company, "country")

    if country != "India":
        return

    # Initialize values
    doc.itc_integrated_tax = (
        doc.itc_state_tax
    ) = doc.itc_central_tax = doc.itc_cess_amount = 0
    gst_accounts = get_gst_accounts(doc.company, only_non_reverse_charge=1)

    for tax in doc.get("taxes"):
        if tax.account_head in gst_accounts.get("igst_account", []):
            doc.itc_integrated_tax += flt(tax.base_tax_amount_after_discount_amount)
        if tax.account_head in gst_accounts.get("sgst_account", []):
            doc.itc_state_tax += flt(tax.base_tax_amount_after_discount_amount)
        if tax.account_head in gst_accounts.get("cgst_account", []):
            doc.itc_central_tax += flt(tax.base_tax_amount_after_discount_amount)
        if tax.account_head in gst_accounts.get("cess_account", []):
            doc.itc_cess_amount += flt(tax.base_tax_amount_after_discount_amount)
