import frappe

from india_compliance.gst_india.doctype.purchase_reconciliation_tool import (
    BaseUtil,
    ReconciledData,
)


def link_documents(purchase_invoice_name, inward_supply_name, link_doctype):
    purchases = []
    inward_supplies = []

    if not purchase_invoice_name or not inward_supply_name:
        return purchases, inward_supplies

    # silently handle existing links
    if isup_linked_with := frappe.db.get_value(
        "GST Inward Supply", inward_supply_name, "link_name"
    ):
        set_reconciliation_status(link_doctype, (isup_linked_with,), "Unreconciled")
        _unlink_documents((inward_supply_name,))
        purchases.append(isup_linked_with)

    link_doc = {
        "link_doctype": link_doctype,
        "link_name": purchase_invoice_name,
    }
    if pur_linked_with := frappe.db.get_all(
        "GST Inward Supply", link_doc, pluck="name"
    ):
        _unlink_documents((pur_linked_with))
        inward_supplies.extend(pur_linked_with)

    link_doc["match_status"] = "Manual Match"

    # link documents
    frappe.db.set_value("GST Inward Supply", inward_supply_name, link_doc)
    set_reconciliation_status(link_doctype, (purchase_invoice_name,), "Match Found")

    purchases.append(purchase_invoice_name)
    inward_supplies.append(inward_supply_name)

    return purchases, inward_supplies


def unlink_documents(data):
    data = frappe.parse_json(data)
    inward_supplies = set()
    purchases = set()
    boe = set()

    for row in data:
        inward_supplies.add(row.get("inward_supply_name"))

        purchase_doctype = row.get("purchase_doctype")
        if purchase_doctype == "Purchase Invoice":
            purchases.add(row.get("purchase_invoice_name"))

        elif purchase_doctype == "Bill of Entry":
            boe.add(row.get("purchase_invoice_name"))

    set_reconciliation_status("Purchase Invoice", purchases, "Unreconciled")
    set_reconciliation_status("Bill of Entry", boe, "Unreconciled")
    _unlink_documents(inward_supplies)

    return purchases.union(boe), inward_supplies


def _unlink_documents(inward_supplies):
    if not inward_supplies:
        return

    GSTR2 = frappe.qb.DocType("GST Inward Supply")
    (
        frappe.qb.update(GSTR2)
        .set("link_doctype", "")
        .set("link_name", "")
        .set("match_status", "Unlinked")
        .where(GSTR2.name.isin(inward_supplies))
        .run()
    )

    # Revert Purchase Reconciliation action performed
    (
        frappe.qb.update(GSTR2)
        .set("action", "No Action")
        .where(GSTR2.name.isin(inward_supplies))
        .where(GSTR2.action.notin(("Ignore", "Pending")))
        .run()
    )

    # Revert IMS action performed
    (
        frappe.qb.update(GSTR2)
        .set("ims_action", "No Action")
        .where(GSTR2.name.isin(inward_supplies))
        .where(GSTR2.ims_action == "Accepted")
        .run()
    )


def get_formatted_options(data):
    for row in data:
        row.value = row.label = row.name
        if not row.get("classification"):
            row.classification = ReconciledData.guess_classification(row)

        row.description = (
            f"{row.bill_no}, {row.bill_date}, Taxable Amount: {row.taxable_value}"
        )
        row.description += (
            f", Tax Amount: {BaseUtil.get_total_tax(row)}, {row.classification}"
        )

    return data


def set_reconciliation_status(doctype, names, status):
    if not names:
        return

    frappe.db.set_value(
        doctype, {"name": ("in", names)}, "reconciliation_status", status
    )
