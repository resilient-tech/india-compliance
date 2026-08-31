from collections import defaultdict

import frappe
from frappe import _

from india_compliance.gst_india.doctype.purchase_reconciliation_tool import (
    BaseUtil,
    ReconciledData,
)
from india_compliance.gst_india.utils.itc_claim import set_itc_claim_period_on_match
from india_compliance.utils.change_log_utils import (
    add_comments_in_bulk,
    create_change_log_comment,
)

SYNCABLE_FIELDS = ("bill_no", "bill_date")

PURCHASE_FIELDNAME_MAP = {
    "Purchase Invoice": {"bill_no": "bill_no", "bill_date": "bill_date"},
    "Bill of Entry": {"bill_no": "bill_of_entry_no", "bill_date": "bill_of_entry_date"},
}


def link_documents(purchase_invoice_name, inward_supply_name, link_doctype):
    purchases = []
    inward_supplies = []

    if not purchase_invoice_name or not inward_supply_name or not link_doctype:
        return purchases, inward_supplies

    # silently handle existing links
    if isup_linked_with := frappe.db.get_value("GST Inward Supply", inward_supply_name, "link_name"):
        set_reconciliation_status(link_doctype, (isup_linked_with,), "Unreconciled")
        _unlink_documents((inward_supply_name,))
        purchases.append(isup_linked_with)

    link_doc = {
        "link_doctype": link_doctype,
        "link_name": purchase_invoice_name,
    }
    if pur_linked_with := frappe.db.get_all("GST Inward Supply", link_doc, pluck="name"):
        _unlink_documents(pur_linked_with)
        inward_supplies.extend(pur_linked_with)

    link_doc["match_status"] = "Manual Match"

    # link documents
    frappe.db.set_value("GST Inward Supply", inward_supply_name, link_doc)
    set_reconciliation_status(link_doctype, (purchase_invoice_name,), "Match Found")

    set_itc_claim_period_on_match(
        [purchase_invoice_name],
        {inward_supply_name: purchase_invoice_name},
        doctype=link_doctype,
    )

    purchases.append(purchase_invoice_name)
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
        if not (row.get("inward_supply_name") and row.get("purchase_invoice_name")):
            continue

        inward_supplies.add(row.get("inward_supply_name"))

        purchase_doctype = row.get("purchase_doctype")
        if purchase_doctype == "Purchase Invoice":
            purchases.add(row.get("purchase_invoice_name"))

        elif purchase_doctype == "Bill of Entry":
            boe.add(row.get("purchase_invoice_name"))

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


def sync_details(data, fields, tool=None):
    """
    Copy bill no / date reported in 2A/2B onto the linked purchase document.
    """
    fields = _validate_sync_fields(fields)

    inward_supply_names = {
        row["inward_supply_name"]
        for row in frappe.parse_json(data)
        # nothing to sync where a side is missing
        if row.get("inward_supply_name") and row.get("purchase_invoice_name")
    }

    if not inward_supply_names:
        frappe.throw(_("Please select matched rows to sync"))

    changes = _get_changes_to_sync(inward_supply_names, fields)

    if not changes:
        frappe.throw(_("No changes to sync"))

    _apply_changes(changes, tool)

    return (
        [change.link_name for change in changes],
        [change.name for change in changes],
    )


def _validate_sync_fields(fields):
    if isinstance(fields, str):
        fields = frappe.parse_json(fields)

    if not fields:
        frappe.throw(_("No fields to sync"))

    if invalid := set(fields) - set(SYNCABLE_FIELDS):
        frappe.throw(_("Unable to sync {0}").format(frappe.bold(", ".join(sorted(invalid)))))

    return [field for field in SYNCABLE_FIELDS if field in fields]


def _get_changes_to_sync(inward_supply_names, fields):
    """
    return:[doctype, name (inward supply), link_name (purchase), {field_name: old_value...}, {field_name: new_value...}]
    """
    changes = []

    for doctype, purchase_fieldnames in PURCHASE_FIELDNAME_MAP.items():
        fieldname_map = {field: purchase_fieldnames[field] for field in fields}

        for row in _get_linked_details(doctype, fieldname_map, inward_supply_names):
            new_values = {
                field_name: reported
                for field_name in fieldname_map.values()
                if (reported := row[f"reported_{field_name}"]) and row[field_name] != reported
            }

            if not new_values:
                continue

            row.new_values = new_values
            row.old_values = {field_name: row[field_name] for field_name in new_values}
            changes.append(row)

    return changes


def _get_linked_details(doctype, fieldname_map, inward_supply_names):
    isup = frappe.qb.DocType("GST Inward Supply")
    purchase = frappe.qb.DocType(doctype)

    return (
        frappe.qb.from_(isup)
        .join(purchase)  # linked purchases only
        .on(purchase.name == isup.link_name)
        .select(
            isup.link_doctype.as_("doctype"),
            isup.name,
            isup.link_name,
            # each field as booked, with what 2A/2B reports for it alongside
            *(purchase[booked].as_(booked) for booked in fieldname_map.values()),
            *(isup[field].as_(f"reported_{booked}") for field, booked in fieldname_map.items()),
        )
        # the stored link decides where the values are booked, not the client
        .where(isup.link_doctype == doctype)
        .where(isup.name.isin(inward_supply_names))
        .run(as_dict=True)
    )


def _apply_changes(changes, tool=None):
    doc_updates_by_doctype = defaultdict(dict)
    comments = []

    for change in changes:
        meta = frappe.get_meta(change.doctype)
        doc_updates_by_doctype[change.doctype][change.link_name] = change.new_values

        comments.append(
            (
                change.doctype,
                change.link_name,
                create_change_log_comment(
                    change.old_values,
                    change.new_values,
                    field_labels={field: meta.get_label(field) for field in change.new_values},
                    date_fields=(PURCHASE_FIELDNAME_MAP[change.doctype]["bill_date"],),
                    source=tool,
                ),
            )
        )

    for doctype, doc_updates in doc_updates_by_doctype.items():
        frappe.db.bulk_update(doctype, doc_updates)

        # bulk_update doesn't invalidate the document cache the way set_value does
        for purchase_name in doc_updates:
            frappe.clear_document_cache(doctype, purchase_name)

    add_comments_in_bulk(comments)


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
