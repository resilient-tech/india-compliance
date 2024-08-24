import frappe


def execute():
    if not frappe.db.table_exists("Bill of Entry Taxes"):
        return

    boe_taxes = frappe.qb.DocType("Bill of Entry Taxes")
    boe_taxes_docs = frappe.qb.from_(boe_taxes).select("*").run(as_dict=True)

    for doc in boe_taxes_docs:
        ic_taxes_doc = frappe.get_doc(
            {
                **doc,
                "doctype": "India Compliance Taxes and Charges",
                "name": None,
                "base_total": doc.total,
            }
        )
        ic_taxes_doc.insert(ignore_if_duplicate=True)

    # Drop the old table
    frappe.db.delete("Bill of Entry Taxes")
