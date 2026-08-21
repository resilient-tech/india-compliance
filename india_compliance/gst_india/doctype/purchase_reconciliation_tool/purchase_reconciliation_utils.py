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


def sync_details(data, fields=None, tool=None):
    """
    Copy bill no / date reported in 2A/2B onto the linked purchase document
    """

    # validate fields
    if not fields:
        fields = ("bill_no", "bill_date")
    elif isinstance(fields, str):
        fields = frappe.parse_json(fields)

    for field in fields:
        if field not in ("bill_no", "bill_date"):
            frappe.throw(_("Invalid field {0}").format(frappe.bold(field)))

    if not fields:
        return [], []

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

    for doctype in {row["purchase_doctype"] for row in rows}:
        frappe.has_permission(doctype, "write", throw=True)

    details_to_sync = _get_details_to_sync(rows, fields)

    updated_purchases = []
    updated_inward_supplies = []
    comments = []

    comment_prefix = _("updated")
    if tool:
        comment_prefix = _("updated using {tool}").replace("{tool}", frappe.bold(_(tool)))

    for row in rows:
        if not (details := details_to_sync.get(row["inward_supply_name"])):
            continue

        booked, reported = details
        doctype = row["purchase_doctype"]
        purchase_name = row["purchase_invoice_name"]

        # replace with actual field names
        billing_fields = BILLING_FIELDS[doctype]
        update = {billing_fields[field]: value for field, value in reported.items()}
        old_values = {billing_fields[field]: value for field, value in booked.items()}

        meta = frappe.get_meta(doctype)
        comments.append(
            (
                doctype,
                purchase_name,
                create_change_log_comment(
                    old_values,
                    update,
                    field_labels={field: meta.get_label(field) for field in update},
                    date_fields=(billing_fields["bill_date"],),
                    comment_prefix=comment_prefix,
                ),
            )
        )

        frappe.db.set_value(doctype, purchase_name, update)

        updated_purchases.append(purchase_name)
        updated_inward_supplies.append(row["inward_supply_name"])

    add_comments_in_bulk(comments)

    return updated_purchases, updated_inward_supplies


def _get_details_to_sync(rows, fields):
    """
    inward supply: (booked values, reported values)
    {inward supply: ({bill_no, bill_date}, {bill_no, bill_date})}.

    Booked values are read from the document, not from the reconciliation row: because they
    fall back to posting date where bill date is not set.
    """

    ## TODO: refactor needed
    inward_supplies = {
        doc.name: doc
        for doc in frappe.get_all(
            "GST Inward Supply",
            filters={"name": ("in", {row["inward_supply_name"] for row in rows})},
            fields=["name", "bill_no", "bill_date"],
        )
    }

    names_by_doctype = {doctype: set() for doctype in BILLING_FIELDS}
    for row in rows:
        names_by_doctype[row["purchase_doctype"]].add(row["purchase_invoice_name"])

    purchases_by_doctype = {doctype: {} for doctype in BILLING_FIELDS}
    for doctype, names in names_by_doctype.items():
        if not names:
            continue

        purchases_by_doctype[doctype] = {
            doc.name: doc
            for doc in frappe.get_all(
                doctype,
                filters={"name": ("in", names)},
                fields=["name", *BILLING_FIELDS[doctype].values()],
            )
        }

    details_to_sync = {}
    for row in rows:
        inward_supply = inward_supplies.get(row["inward_supply_name"])
        purchase = purchases_by_doctype[row["purchase_doctype"]].get(row["purchase_invoice_name"])
        if not inward_supply or not purchase:
            continue

        billing_fields = BILLING_FIELDS[row["purchase_doctype"]]

        booked = {}
        reported = {}
        for reported_field in fields:
            field = billing_fields[reported_field]
            reported_value = inward_supply.get(reported_field)

            if not reported_value or purchase.get(field) == reported_value:
                continue

            booked[reported_field] = purchase.get(field)
            reported[reported_field] = reported_value

        if reported:
            details_to_sync[row["inward_supply_name"]] = (booked, reported)

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
