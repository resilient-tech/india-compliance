import frappe

DOCTYPES = (
    "Sales Invoice",
    "Delivery Note",
    "POS Invoice",
    "Sales Order",
)


def execute():
    column = "customer_gstin"

    delete_old_fields()
    for doctype in DOCTYPES:
        if column not in frappe.db.get_table_columns(doctype):
            continue

        doc_type = frappe.qb.DocType(doctype)
        frappe.qb.update(doc_type).set(
            doc_type.shipping_address_gstin, doc_type.customer_gstin
        ).where(doc_type.customer_gstin.notin(("", None))).run()

        frappe.db.sql_ddl(
            "alter table `tab{0}` drop column {1}".format(doctype, column)
        )


def delete_old_fields():
    frappe.db.delete(
        "Custom Field", {"fieldname": "customer_gstin", "dt": ("in", DOCTYPES)}
    )
