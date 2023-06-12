import frappe

from india_compliance.gst_india.setup import _create_hsn_codes

DOCTYPE = "GST HSN Code"
INCORRECT_HSN_CODE_LENGTHS = frozenset((3, 5, 7))


def execute():
    if frappe.flags.hsn_codes_corrected:
        return

    used_hsn_codes = get_used_hsn_codes()
    frappe.db.delete(DOCTYPE, {"name": ("not in", used_hsn_codes)})
    _create_hsn_codes()

    new_hsn_codes = get_new_hsn_codes(used_hsn_codes)
    if not new_hsn_codes:
        return

    rename_hsn_codes(new_hsn_codes)


def rename_hsn_codes(new_hsn_codes):
    existing_hsn_codes = set(
        frappe.get_all(
            DOCTYPE,
            filters={"name": ("in", new_hsn_codes)},
            pluck="name",
        )
    )

    count = 0
    commit_interval = 100

    for hsn_code in new_hsn_codes:
        merge = hsn_code in existing_hsn_codes
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


def get_used_hsn_codes():
    used_hsn_codes = frappe.get_all(
        "Item",
        filters={"gst_hsn_code": ("!=", "")},
        distinct=True,
        pluck="gst_hsn_code",
    )

    used_hsn_codes = frappe.get_all(
        DOCTYPE,
        filters={"name": ("in", used_hsn_codes)},
        pluck="name",
    )

    return used_hsn_codes


def get_new_hsn_codes(used_hsn_codes):
    new_hsn_codes = set()

    for hsn_code in used_hsn_codes:
        length = len(hsn_code)

        if length not in INCORRECT_HSN_CODE_LENGTHS:
            continue

        new_hsn_codes.add(hsn_code.zfill(length + 1))

    return new_hsn_codes
