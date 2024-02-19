import frappe
from frappe.query_builder.functions import Coalesce
from frappe.utils import sbool


def execute():
    # Sales Invoice should have field signed_einvoice
    # and E Invoice Settings should be enabled

    if not frappe.db.has_column("Sales Invoice", "signed_einvoice") or not sbool(
        frappe.db.get_value(
            "E Invoice Settings", "E Invoice Settings", "enable", ignore=True
        )
    ):
        set_not_applicable_status()
        return

    frappe.db.sql(
        """
        UPDATE `tabSales Invoice` SET einvoice_status = 'Pending'
        WHERE
            IFNULL(einvoice_status, '') = ''
            AND posting_date >= '2021-04-01'
            AND docstatus = 1
            AND IFNULL(irn, '') = ''
            AND IFNULL(billing_address_gstin, '') != IFNULL(company_gstin, '')
            AND IFNULL(gst_category, '') in ('Registered Regular', 'SEZ', 'Overseas', 'Deemed Export')
    """
    )

    frappe.db.sql(
        """UPDATE `tabSales Invoice` SET einvoice_status = 'Generated'
        WHERE
            IFNULL(einvoice_status, '') = ''
            AND IFNULL(irn, '') != ''
            AND IFNULL(irn_cancelled, 0) = 0"""
    )

    frappe.db.sql(
        """UPDATE `tabSales Invoice` SET einvoice_status = 'Cancelled'
        WHERE IFNULL(einvoice_status, '') = '' AND IFNULL(irn_cancelled, 0) = 1"""
    )

    update_status_for_cancelled_invoice()
    set_not_applicable_status()


def set_not_applicable_status():
    sales_invoice = frappe.qb.DocType("Sales Invoice")

    frappe.qb.update(sales_invoice).set("einvoice_status", "Not Applicable").where(
        (sales_invoice.docstatus != 0)
        & (Coalesce(sales_invoice.einvoice_status, "") == "")
        & (Coalesce(sales_invoice.irn, "") == "")
    ).run()


def update_status_for_cancelled_invoice():
    sales_invoice = frappe.qb.DocType("Sales Invoice")
    frappe.qb.update(sales_invoice).set(
        "einvoice_status", "Pending Cancellation"
    ).where((sales_invoice.docstatus == 2) & (sales_invoice.irn != "")).run()


@frappe.whitelist()
def after_changing_gst_settings_change_status(company, e_invoice_applicable_from):

    gst_settings = frappe.get_doc("GST Settings")
    if not gst_settings.enable_e_invoice:
        return

    sales_invoice = frappe.qb.DocType("Sales Invoice")
    sales_invoice_item = frappe.qb.DocType("Sales Invoice Item")

    query = (
        frappe.qb.update(sales_invoice)
        .join(sales_invoice_item)
        .on(sales_invoice_item.parent == sales_invoice.name)
        .set(sales_invoice.einvoice_status, "Pending")
        .where(sales_invoice_item.gst_treatment.isin(("Taxable", "Zero-Rated")))
        .where(
            sales_invoice.einvoice_status.notnull() & sales_invoice.einvoice_status
            == "Not Applicable"
        )
        .where(sales_invoice.posting_date >= e_invoice_applicable_from)
        .where(sales_invoice.docstatus == 1)
        .where(sales_invoice.irn.notnull() & sales_invoice.irn == "")
        .where(
            sales_invoice.billing_address_gstin.notnull()
            & sales_invoice.company_gstin.notnull()
            & sales_invoice.billing_address_gstin
            != sales_invoice.company_gstin
        )
        .where(
            sales_invoice.gst_category.notnull()
            & sales_invoice.gst_category.isin(
                ("Registered Regular", "SEZ", "Overseas", "Deemed Export")
            )
        )
        .where(
            (
                sales_invoice.place_of_supply.notnull() & sales_invoice.place_of_supply
                == "96-Other Countries"
            )
            | (
                sales_invoice.billing_address_gstin.notnull()
                & sales_invoice.billing_address_gstin
                != ""
            )
        )
    )

    if company:
        query = query.where(sales_invoice.company == company)

    query.run()
