import frappe


def toggle_custom_fields(custom_fields, show):
    """
    Show / hide custom fields

    :param custom_fields: a dict like `{'Sales Invoice': [{fieldname: 'test', ...}]}`
    :param show: True to show fields, False to hide
    """

    for doctypes, fields in custom_fields.items():
        if isinstance(fields, dict):
            # only one field
            fields = [fields]

        if isinstance(doctypes, str):
            # only one doctype
            doctypes = (doctypes,)

        for doctype in doctypes:
            frappe.db.set_value(
                "Custom Field",
                {
                    "dt": doctype,
                    "fieldname": ["in", [field["fieldname"] for field in fields]],
                },
                "hidden",
                int(not show),
            )

            frappe.clear_cache(doctype=doctype)


def delete_old_fields(fieldnames, doctypes):
    if isinstance(fieldnames, str):
        fieldnames = (fieldnames,)

    if isinstance(doctypes, str):
        doctypes = (doctypes,)

    frappe.db.delete(
        "Custom Field",
        {
            "fieldname": ("in", fieldnames),
            "dt": ("in", doctypes),
        },
    )


def delete_custom_fields(custom_fields):
    """
    :param custom_fields: a dict like `{'Sales Invoice': [{fieldname: 'test', ...}]}`
    """

    for doctypes, fields in custom_fields.items():
        if isinstance(fields, dict):
            # only one field
            fields = [fields]

        if isinstance(doctypes, str):
            # only one doctype
            doctypes = (doctypes,)

        for doctype in doctypes:
            frappe.db.delete(
                "Custom Field",
                {
                    "fieldname": ("in", [field["fieldname"] for field in fields]),
                    "dt": doctype,
                },
            )

            frappe.clear_cache(doctype=doctype)
