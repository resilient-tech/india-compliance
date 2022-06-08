import frappe

DOCTYPES = (
    "Sales Invoice",
    "Delivery Note",
    "POS Invoice",
    "Sales Order",
    "Payment Entry",
)


def execute():
    column = "customer_gstin"

    delete_old_fields()
    for doctype in DOCTYPES:
        if column not in frappe.db.get_table_columns(doctype):
            continue

        customer_gstins = {}
        for party in frappe.db.get_all(doctype, fields=["name", "customer_gstin"]):
            customer_gstins.setdefault((doctype, party.customer_gstin), []).append(
                party.name
            )

    for (doctype, customer_gstin), docnames in customer_gstins.items():
        frappe.db.set_value(
            doctype,
            {"name": ("in", docnames)},
            "shipping_address_gstin",
            customer_gstin,
        )
        frappe.db.sql_ddl(
            "alter table `tab{0}` drop column {1}".format(doctype, column)
        )


def delete_old_fields():
    frappe.db.delete(
        "Custom Field", {"fieldname": "customer_gstin", "dt": ("in", DOCTYPES)}
    )
