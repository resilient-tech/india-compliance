import frappe

from india_compliance.gst_india.setup import _create_hsn_codes

DOCTYPE = "GST HSN Code"


def execute():
    if frappe.flags.hsn_codes_corrected:
        return

    used_hsn_code = frappe.get_all(
        "Item",
        filters={"gst_hsn_code": ("!=", "")},
        distinct=True,
        pluck="gst_hsn_code",
    )

    frappe.db.delete(DOCTYPE, {"name": ("not in", used_hsn_code)})
    _create_hsn_codes()

    new_hsn_code = set()

    for hsn_code in used_hsn_code:
        length = len(hsn_code)

        if length not in (3, 5, 7):
            continue

        new_hsn_code.add(hsn_code.zfill(length + 1))

    exisitng_hsn_code = set(
        frappe.get_all(
            DOCTYPE,
            filters={"name": ("in", list(new_hsn_code))},
            pluck="name",
        )
    )

    count = 0
    commit_interval = 100

    for hsn_code in new_hsn_code:
        merge = hsn_code in exisitng_hsn_code
        frappe.rename_doc(
            DOCTYPE,
            hsn_code[1:],
            hsn_code,
            force=True,
            merge=merge,
            rebuild_search=False,
        )

        count += 1

        if count % commit_interval == 0:
            frappe.db.commit()

    frappe.enqueue("frappe.utils.global_search.rebuild_for_doctype", doctype=DOCTYPE)
