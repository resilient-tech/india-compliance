import frappe
from frappe import _
from frappe.query_builder import Criterion
from frappe.query_builder.functions import IfNull

from india_compliance.gst_india.doctype.purchase_reconciliation_tool import (
    BaseUtil,
    ReconciledData,
)
from india_compliance.gst_india.utils.itc_claim import set_itc_claim_period_on_match
from india_compliance.utils.change_log_utils import (
    add_comments_in_bulk,
    create_change_log_comment,
)

# as reported in 2A/2B, mapped to where the purchase document books them
BILLING_FIELDS = {
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
    Copy bill no / date reported in 2A/2B onto the linked purchase document
    """
    for doctype in BILLING_FIELDS.keys():
        frappe.has_permission(doctype, "write", throw=True)

    if isinstance(fields, str):
        fields = frappe.parse_json(fields)

    if not fields:
        frappe.throw(_("No fields to sync"))

    if invalid := set(fields) - set(next(iter(BILLING_FIELDS.values()))):
        frappe.throw(_("Unable to sync {0}").format(frappe.bold(", ".join(invalid))))

    # validate data
    data = frappe.parse_json(data)
    rows = [
        row
        for row in data
        if row.get("inward_supply_name")
        and row.get("purchase_invoice_name")
        and row.get("purchase_doctype") in BILLING_FIELDS
    ]

    if not rows:
        return [], []

    details_to_sync = _get_details_to_sync(rows, fields)

    updated_purchases = []
    updated_inward_supplies = []
    comments = []
    comment_prefix = _("updated")
    if tool:
        comment_prefix = _("updated using {tool}").replace("{tool}", frappe.bold(_(tool)))
    doc_updates_by_doctype = {}

    for row in details_to_sync:
        doctype = row.get("doctype")
        billing_fields = BILLING_FIELDS[doctype]

        update = {billing_fields[field]: row.get(field) for field in fields}
        old_values = {billing_fields[field]: row.get(f"booked_{field}") for field in fields}

        meta = frappe.get_meta(doctype)
        comments.append(
            (
                doctype,
                row.link_name,
                create_change_log_comment(
                    old_values,
                    update,
                    field_labels={field: meta.get_label(field) for field in update},
                    date_fields=(billing_fields["bill_date"],),
                    comment_prefix=comment_prefix,
                ),
            )
        )

        doc_updates_by_doctype.setdefault(doctype, {})[row.link_name] = update
        updated_purchases.append(row.link_name)
        updated_inward_supplies.append(row.name)

    for doctype, doc_updates in doc_updates_by_doctype.items():
        frappe.db.bulk_update(doctype, doc_updates)

        # bulk_update doesn't invalidate the document cache the way set_value does
        for purchase_name in doc_updates:
            frappe.clear_document_cache(doctype, purchase_name)

    add_comments_in_bulk(comments)

    return updated_purchases, updated_inward_supplies


def _get_details_to_sync(rows, fields):
    """
    One row per linked inward supply:
    {doctype, name (inward supply), link_name (purchase),
     <reported fields>, booked_<fields> (values booked on the purchase document)}
    """
    inward_supply_names = {row["inward_supply_name"] for row in rows}

    isup = frappe.qb.DocType("GST Inward Supply")

    details_to_sync = []
    for doctype, billing_fields in BILLING_FIELDS.items():
        purchase = frappe.qb.DocType(doctype)

        # at least one reported value is set and differs from the booked value
        has_difference = Criterion.any(
            (IfNull(isup[field], "") != "")
            & (IfNull(purchase[billing_fields[field]], "") != IfNull(isup[field], ""))
            for field in fields
        )

        details_to_sync.extend(
            frappe.qb.from_(isup)
            .join(purchase)  # linked purchases only
            .on((purchase.name == isup.link_name) & (isup.link_doctype == doctype))
            .select(
                isup.link_doctype.as_("doctype"),
                isup.name,
                isup.link_name,
                *(isup[field] for field in fields),
                *(purchase[billing_fields[field]].as_(f"booked_{field}") for field in fields),
            )
            .where(isup.name.isin(inward_supply_names))
            .where(has_difference)
            .run(as_dict=True)
        )

    return details_to_sync


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
