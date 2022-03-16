import json

import frappe


def execute():
    if frappe.db.exists("E Invoice Settings") and frappe.db.get_single_value(
        "E Invoice Settings", "enable"
    ):
        frappe.db.sql(
            """
            UPDATE `tabSales Invoice` SET einvoice_status = 'Pending'
            WHERE
                posting_date >= '2021-04-01'
                AND ifnull(irn, '') = ''
                AND ifnull(billing_address_gstin, '') != ifnull(company_gstin, '')
                AND ifnull(gst_category, '') in ('Registered Regular', 'SEZ', 'Overseas', 'Deemed Export')
        """
        )

        # set appropriate statuses
        frappe.db.sql(
            """UPDATE `tabSales Invoice` SET einvoice_status = 'Generated'
            WHERE ifnull(irn, '') != '' AND ifnull(irn_cancelled, 0) = 0"""
        )

        frappe.db.sql(
            """UPDATE `tabSales Invoice` SET einvoice_status = 'Cancelled'
            WHERE ifnull(irn_cancelled, 0) = 1"""
        )

    # set correct acknowledgement in e-invoices
    for name, signed_einvoice in frappe.get_all(
        "Sales Invoice", {"irn": ("is", "set")}, ("name", "signed_einvoice")
    ):
        if not signed_einvoice:
            continue

        signed_einvoice = json.loads(signed_einvoice)
        frappe.db.set_value(
            "Sales Invoice",
            name,
            {
                "ack_no": signed_einvoice.get("AckNo"),
                "ack_date": signed_einvoice.get("AckDt"),
            },
            update_modified=False,
        )
