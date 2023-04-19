import frappe

from india_compliance.gst_india.setup import _create_hsn_codes


def execute():
    # using db.get_value instead of db.get_global because cache is not cleared.
    is_hsn_code_updated = frappe.db.get_value(
        "DefaultValue",
        {
            "parent": "__global",
            "defkey": "updated_hsn_code",
        },
        "defvalue",
    )

    if is_hsn_code_updated == "1":
        return

    used_hsn_code = frappe.get_all(
        "Item",
        fields=["gst_hsn_code"],
        filters={"gst_hsn_code": ("!=", "")},
        distinct=True,
        pluck="gst_hsn_code",
    )

    frappe.db.delete("GST HSN Code", {"name": ("not in", used_hsn_code)})
    _create_hsn_codes()

    for hsn_code in used_hsn_code:
        length = len(hsn_code)

        if length not in [3, 5, 7]:
            continue

        new_hsn = hsn_code.zfill(length + 1)

        if frappe.db.exists("GST HSN Code", new_hsn):
            frappe.rename_doc("GST HSN Code", hsn_code, new_hsn, force=True, merge=True)
        else:
            frappe.rename_doc("GST HSN Code", hsn_code, new_hsn, force=True)
