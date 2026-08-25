import frappe

from india_compliance.gst_india.doctype.purchase_reconciliation_tool import (
    BaseUtil,
    ReconciledData,
)
from india_compliance.gst_india.utils.itc_claim import set_itc_claim_period_on_match


def link_documents(linked_doc, inward_supply_name, link_doctype):
    purchases = []
    inward_supplies = []

    if not linked_doc or not inward_supply_name or not link_doctype:
        return purchases, inward_supplies

    # silently handle existing links
    if isup_linked_with := frappe.db.get_value("GST Inward Supply", inward_supply_name, "link_name"):
        set_reconciliation_status(link_doctype, (isup_linked_with,), "Unreconciled")
        _unlink_documents((inward_supply_name,))
        purchases.append(isup_linked_with)

    link_doc = {
        "link_doctype": link_doctype,
        "link_name": linked_doc,
    }
    if pur_linked_with := frappe.db.get_all("GST Inward Supply", link_doc, pluck="name"):
        _unlink_documents(pur_linked_with)
        inward_supplies.extend(pur_linked_with)

    link_doc["match_status"] = "Manual Match"

    # link documents
    frappe.db.set_value("GST Inward Supply", inward_supply_name, link_doc)
    set_reconciliation_status(link_doctype, (linked_doc,), "Match Found")

    set_itc_claim_period_on_match(
        [linked_doc],
        {inward_supply_name: linked_doc},
        doctype=link_doctype,
    )

    purchases.append(linked_doc)
    inward_supplies.append(inward_supply_name)

    return purchases, inward_supplies


def unlink_documents(data, exclude_from_reconciliation=False):
    data = frappe.parse_json(data)
    exclude_from_reconciliation = frappe.parse_json(exclude_from_reconciliation)
    inward_supplies = set()
    purchases = set()
    boe = set()

    for row in data:
        # nothing to unlink where a side is missing
        if not (row.get("inward_supply_name") and row.get("linked_doc")):
            continue

        inward_supplies.add(row.get("inward_supply_name"))

        linked_voucher_type = row.get("linked_voucher_type")
        if linked_voucher_type == "Purchase Invoice":
            purchases.add(row.get("linked_doc"))

        elif linked_voucher_type == "Bill of Entry":
            boe.add(row.get("linked_doc"))

    set_reconciliation_status("Purchase Invoice", purchases, "Unreconciled")
    set_reconciliation_status("Bill of Entry", boe, "Unreconciled")
    _unlink_documents(inward_supplies, exclude_from_reconciliation)

    # keep itc_claim_period, user can change it

    return purchases.union(boe), inward_supplies


def _unlink_documents(inward_supplies, exclude_from_reconciliation=False):
    if not inward_supplies:
        return

    # blank status = match again next run. "Unlinked" = leave it alone
    match_status = "Unlinked" if exclude_from_reconciliation else ""

    GSTR2 = frappe.qb.DocType("GST Inward Supply")
    (
        frappe.qb.update(GSTR2)
        .set("link_doctype", "")
        .set("link_name", "")
        .set("match_status", match_status)
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

        row.description = f"{row.bill_no}, {row.bill_date}, Taxable Amount: {row.taxable_value}"
        row.description += f", Tax Amount: {BaseUtil.get_total_tax(row)}, {row.classification}"

    return data


def set_reconciliation_status(doctype, names, status):
    if not names:
        return

    frappe.db.set_value(doctype, {"name": ("in", names)}, "reconciliation_status", status)
