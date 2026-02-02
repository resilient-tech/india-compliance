import frappe
from frappe import _
from frappe.utils import escape_html, get_date_str, get_fullname


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
