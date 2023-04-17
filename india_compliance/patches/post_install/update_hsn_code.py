import frappe

from india_compliance.gst_india.setup import create_hsn_codes


def execute():
    x = frappe.db.get_value(
        "DefaultValue",
        {
            "parent": "__global",
            "defkey": "updated_hsn_code",
        },
        "defvalue",
    )
    if x == "1":
        return

    # used hsn in items
    used_hsn_code = frappe.db.sql_list(
        """select distinct gst_hsn_code from `tabItem` where gst_hsn_code is not null and gst_hsn_code != ''"""
    )

    # remove all hsn except used_hsn list
    frappe.db.delete("GST HSN Code", {"name": ("not in", used_hsn_code)})

    if used_hsn_code:
        for hsn_code in used_hsn_code:
            length = len(hsn_code)

            if length in [3, 5, 7]:
                new_hsn = hsn_code.zfill(length + 1)

                if frappe.db.exists("GST HSN Code", new_hsn):
                    frappe.rename_doc(
                        "GST HSN Code", hsn_code, new_hsn, force=True, merge=True
                    )
                else:
                    frappe.rename_doc("GST HSN Code", hsn_code, new_hsn, force=True)

    # create new hsn code
    create_hsn_codes()
