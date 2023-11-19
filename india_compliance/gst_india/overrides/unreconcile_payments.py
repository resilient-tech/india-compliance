import frappe
from erpnext.accounts.general_ledger import make_reverse_gl_entries


def before_submit(doc, method=None):
    if doc.voucher_type != "Payment Entry":
        return

    for allocation in doc.allocations:
        voucher_detail_nos = frappe.get_all(
            "Payment Entry Reference",
            {
                "parent": doc.voucher_no,
                "reference_doctype": allocation.reference_doctype,
                "reference_name": allocation.reference_name,
                "docstatus": 1,
            },
            pluck="name",
        )

        for voucher_detail_no in voucher_detail_nos:
            reverse_gst_adjusted_against_payment_entry(
                voucher_detail_no, doc.voucher_no
            )


def reverse_gst_adjusted_against_payment_entry(voucher_detail_no, payment_name):
    filters = {
        "voucher_type": "Payment Entry",
        "voucher_no": payment_name,
        "voucher_detail_no": voucher_detail_no,
    }

    gl_entries = frappe.get_all("GL Entry", filters=filters, fields="*")
    if not gl_entries:
        return

    frappe.db.set_value("GL Entry", filters, "is_cancelled", 1)
    make_reverse_gl_entries(gl_entries, partial_cancel=True)
