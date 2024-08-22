import frappe


def execute():
    if not frappe.db.table_exists("GSTR-1 Log"):
        return

    old = frappe.qb.DocType("GSTR-1 Log")
    old_docs = frappe.qb.from_(old).select("*").run(as_dict=True)

    for doc in old_docs:
        new_doc = frappe.get_doc(
            {**doc, "doctype": "GST Return Log", "name": None, "return_type": "GSTR1"}
        )
        new_doc.insert(ignore_if_duplicate=True)

    # Drop the old table
    frappe.db.delete("GSTR-1 Log")

    # Clear all fields saved in GSTR-1 Beta
    frappe.db.delete("Singles", {"doctype": "GSTR-1 Beta"})
