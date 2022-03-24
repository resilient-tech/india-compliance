import json

import frappe
from frappe.utils import sbool


def execute():
    if not sbool(frappe.db.get_value("E Invoice Settings", None, "enable")):
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

        # set appropriate statuses
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

    # set correct acknowledgement in e-invoices
    for name, signed_einvoice in frappe.get_all(
        "Sales Invoice",
        {"ack_no": ("is", "not set"), "irn": ("is", "set")},
        ("name", "signed_einvoice"),
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
