from collections.abc import Iterable
from uuid import uuid7

import frappe
from frappe import _
from frappe.model.document import bulk_insert
from frappe.utils import cast, escape_html, get_date_str, get_fullname


def add_versions_in_bulk(
    versions: Iterable[tuple[str, str, dict, dict]],
    *,
    updater_reference: dict | None = None,
    user: str | None = None,
    timestamp: str | None = None,
) -> None:
    """
    Record a timeline entry for documents written outside the document API, as
    frappe.db.set_value and frappe.db.bulk_update leave none behind.

    Args:
        versions: (doctype, docname, old_values, new_values), each a {fieldname: value}
            of what the written fields held before and after.
        updater_reference: {"doctype", "docname"} of the tool making the change.

    The entry is Version.set_diff's own, built from documents assembled in memory, so
    it carries whatever a save would have recorded. A doctype that does not track
    changes, and a field that ignores versioning, are left out as a save leaves them.
    """

    user = user or frappe.session.user
    timestamp = timestamp or frappe.utils.now()

    version_docs = []

    for doctype, docname, old_values, new_values in versions:
        if not frappe.get_meta(doctype).track_changes:
            continue

        booked = frappe.get_doc({"doctype": doctype, "name": docname, **old_values})
        updated = frappe.get_doc({"doctype": doctype, "name": docname, **old_values, **new_values})
        updated.flags.updater_reference = updater_reference

        version = frappe.new_doc("Version")
        if not version.set_diff(booked, updated):
            continue

        version.update(
            {
                "name": str(uuid7()),
                "creation": timestamp,
                "modified": timestamp,
                "modified_by": user,
                "owner": user,
            }
        )
        version_docs.append(version)

    if not version_docs:
        return

    bulk_insert("Version", version_docs, ignore_duplicates=True)


def validate_update_access(doctype: str, fieldnames: Iterable[str]) -> None:
    """Throw unless the user may write these fields of doctype, checked on the
    doctype and not on any one document."""

    frappe.has_permission(doctype, "write", throw=True)

    if frappe.session.user == "Administrator":
        return

    meta = frappe.get_meta(doctype)
    restricted = set(fieldnames) - set(meta.get_permitted_fieldnames(permission_type="write"))

    if not restricted:
        return

    frappe.throw(
        _("No permission to update {0} in {1}").format(
            frappe.bold(", ".join(meta.get_label(fieldname) for fieldname in sorted(restricted))),
            _(doctype),
        ),
        frappe.PermissionError,
    )


def update_docs(
    doctype: str,
    docs: dict[str, dict],
    *,
    ignore_version: bool = False,
    updater_reference: dict | None = None,
    check_permission: bool = True,
) -> list[str]:
    """
    Update fields on many documents at once, and record each change on the timeline.

    Args:
        docs: {docname: {fieldname: new_value}}, as frappe.db.bulk_update takes it.
            One document is a one entry dict, and costs no more than it should.
        ignore_version: skip the timeline, as doc.save(ignore_version=True) does.
        updater_reference: {"doctype", "docname"} of the tool making the change.

    Returns the names written, skipping documents already holding the value.

    The timeline entry is Version.set_diff's own, built from documents assembled in
    memory, so it carries whatever a save would have recorded.

    Runs no hooks and no validations, as frappe.db.bulk_update does: the caller
    validates, and checks any permission beyond validate_update_access.
    """

    if not docs:
        return []

    meta = frappe.get_meta(doctype)

    fieldnames = set()
    for new_values in docs.values():
        fieldnames.update(new_values)

    # standard columns are not doctype fields either, so this covers them too
    if invalid := sorted(fieldname for fieldname in fieldnames if not meta.get_field(fieldname)):
        frappe.throw(_("{0} is not a valid field of {1}").format(frappe.bold(", ".join(invalid)), _(doctype)))

    if check_permission:
        validate_update_access(doctype, fieldnames)

    db_rows = frappe.get_all(doctype, filters={"name": ("in", list(docs))}, fields=["name", *fieldnames])
    db_values = {row.name: row for row in db_rows}

    user = frappe.session.user
    timestamp = frappe.utils.now()

    changed_docs = {}
    versions = []

    for docname, new_values in docs.items():
        db_row = db_values.get(docname)
        if db_row is None:
            continue

        changed = {}

        for fieldname, new_value in new_values.items():
            df = meta.get_field(fieldname)

            if cast(df.fieldtype, db_row.get(fieldname)) == cast(df.fieldtype, new_value):
                continue

            changed[fieldname] = new_value

        if not changed:
            continue

        changed_docs[docname] = changed
        versions.append((doctype, docname, db_row, changed))

    if not changed_docs:
        return []

    frappe.db.bulk_update(doctype, changed_docs, modified=timestamp, modified_by=user)

    # bulk_update leaves the document cache behind, unlike db.set_value
    for docname in changed_docs:
        frappe.clear_document_cache(doctype, docname)

    if not ignore_version:
        add_versions_in_bulk(versions, updater_reference=updater_reference, user=user, timestamp=timestamp)

    return list(changed_docs)


def create_change_log_comment(
    old_values,
    new_values,
    field_labels=None,
    date_fields=None,
    comment_prefix=None,
    user=None,
):
    """
    Generate an HTML comment showing field changes.

    Args:
        old_values (dict): Dictionary of old field values
        new_values (dict): Dictionary of new field values
        field_labels (dict): Optional mapping of field names to display labels
        date_fields (list/tuple): Optional list of fields to format as dates
        comment_prefix (str): Optional comment prefix (default: "Updated by {user}")
        user (str): Optional user name (default: current user)

    Returns:
        str: HTML formatted comment or None if no changes
    """
    field_labels = field_labels or {}
    date_fields = date_fields or []

    # Find changed fields
    changed_fields = []
    all_fields = set(old_values.keys()) | set(new_values.keys())

    for field in all_fields:
        # Skip if field not in labels map when labels are provided
        if field_labels and field not in field_labels:
            continue

        old_val, new_val = old_values.get(field), new_values.get(field)

        # Format dates
        if field in date_fields:
            old_val = old_val and get_date_str(old_val)
            new_val = new_val and get_date_str(new_val)

        # Skip unchanged fields
        if old_val == new_val:
            continue

        # Get display label
        label = field_labels.get(field, field.replace("_", " ").title())

        # Format values
        old_display = "<empty>" if old_val is None else str(old_val)
        new_display = "<empty>" if new_val is None else str(new_val)

        changed_fields.append((label, old_display, new_display))

    if not changed_fields:
        return None

    # Build comment
    user = user or get_fullname()
    prefix = comment_prefix or _("Updated by {user}")
    comment_header = (prefix + ".<br><br>").format(user=frappe.bold(user))

    # Build table
    table_rows = "".join(
        [
            f"<tr><td>{frappe.bold(_(label))}</td><td>{escape_html(old_val)}</td><td>{escape_html(new_val)}</td></tr>"
            for label, old_val, new_val in changed_fields
        ]
    )

    table = f"""
    <table class="table table-bordered">
        <thead>
            <tr>
                <th>{_("Field")}</th>
                <th>{_("From")}</th>
                <th>{_("To")}</th>
            </tr>
        </thead>
        <tbody>
            {table_rows}
        </tbody>
    </table>
    """

    return comment_header + table
