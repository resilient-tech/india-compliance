import frappe


def execute():
    """
    Match status was not being updated when manually matched. This patch will update the reconciliation status.
    """
    inward_supply = frappe.qb.DocType("GST Inward Supply")
    docs = (
        frappe.qb.from_(inward_supply)
        .select(inward_supply.link_doctype, inward_supply.link_name)
        .where(inward_supply.link_doctype.isin(("Purchase Invoice", "Bill of Entry")))
        .where(inward_supply.action == "No Action")  # status updated on action
        .where(inward_supply.match_status == "Manual Match")
        .run(as_dict=True)
    )

    docs_to_update = {}

    for doc in docs:
        docs_to_update.setdefault(doc.link_doctype, []).append(doc.link_name)

    for doctype, doc_names in docs_to_update.items():
        frappe.db.set_value(
            doctype, {"name": ("in", doc_names)}, "reconciliation_status", "Match Found"
        )
