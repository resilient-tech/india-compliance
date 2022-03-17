import frappe

from erpnext.controllers.taxes_and_totals import get_itemised_tax_breakup_html


def execute():
    companies = frappe.db.sql_list(
        "select name from tabCompany where country = 'India'"
    )
    if not companies:
        return

    companies_str = ", ".join(map(frappe.db.escape, companies))
    for doctype in (
        "Quotation",
        "Sales Order",
        "Delivery Note",
        "Sales Invoice",
        "Supplier Quotation",
        "Purchase Order",
        "Purchase Receipt",
        "Purchase Invoice",
    ):
        date_field = "posting_date"
        if doctype in (
            "Quotation",
            "Sales Order",
            "Supplier Quotation",
            "Purchase Order",
        ):
            date_field = "transaction_date"

        transactions = frappe.db.sql(
            """
            SELECT dt.name, dt_item.name AS child_name
            FROM `tab{doctype}` dt, `tab{doctype} Item` dt_item
            WHERE dt.name = dt_item.parent
                AND dt.`{date_field}` > '2018-06-01'
                AND dt.docstatus = 1
                AND IFNULL(dt_item.gst_hsn_code, '') = ''
                AND IFNULL(dt_item.item_code, '') != ''
                AND dt.company in ({companies})
        """.format(
                doctype=doctype,
                date_field=date_field,
                companies=companies_str,
            ),
            as_dict=True,
        )

        if not transactions:
            continue

        frappe.db.sql(
            """
            UPDATE `tab{doctype} Item` dt_item
            SET dt_item.gst_hsn_code = (SELECT gst_hsn_code FROM tabItem WHERE name=dt_item.item_code)
            WHERE dt_item.name in ({rows_name})
        """.format(
                doctype=doctype,
                rows_name=", ".join(
                    frappe.db.escape(d.child_name) for d in transactions
                ),
            ),
        )

        for transaction in transactions:
            doc = frappe.get_doc(doctype, transaction.name)
            doc.db_set(
                "other_charges_calculation",
                get_itemised_tax_breakup_html(doc),
                update_modified=False,
            )
