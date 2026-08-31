import frappe
from frappe import _
from frappe.model.document import bulk_insert
from frappe.utils import escape_html, get_date_str, get_fullname, random_string


def add_comments_in_bulk(comments, comment_type="Info", user=None, timestamp=None):
    """
    Insert timeline comments for many documents at once.

    Args:
        comments: iterable of (reference_doctype, reference_name, content).
            Rows with no content are skipped, so a change log comment that came
            back empty can be passed straight through.

    Returns:
        int: number of comments inserted

    Bypasses all hooks, as bulk_insert does. Use only for informational comments.
    """
    user = user or frappe.session.user
    timestamp = timestamp or frappe.utils.now()

    comment_docs = [
        frappe.new_doc("Comment").update(
            {
                "name": random_string(10),
                "comment_type": comment_type,
                "comment_email": user,
                "comment_by": user,
                "creation": timestamp,
                "modified": timestamp,
                "modified_by": user,
                "owner": user,
                "reference_doctype": doctype,
                "reference_name": name,
                "content": content,
            }
        )
        for doctype, name, content in comments
        if content
    ]

    if not comment_docs:
        return 0

    bulk_insert("Comment", comment_docs, ignore_duplicates=True)

    return len(comment_docs)


def create_change_log_comment(
    old_values,
    new_values,
    field_labels=None,
    date_fields=None,
    comment_prefix=None,
    source=None,
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
        source (str): Optional tool the change came from, named alongside the user
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
    prefix = comment_prefix or (_("Updated by {user} using {source}") if source else _("Updated by {user}"))
    comment_header = (prefix + ".<br><br>").format(
        user=frappe.bold(user), source=frappe.bold(_(source)) if source else ""
    )

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
