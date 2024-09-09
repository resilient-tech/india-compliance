import frappe

from india_compliance.gst_india.utils import get_gstin_list


def execute():
    if not frappe.db.has_column("GSTR 3B Report", "month"):
        return

    # Update month_or_quarter from month field
    gstr3b_report = frappe.qb.DocType("GSTR 3B Report")

    (
        frappe.qb.update(gstr3b_report)
        .set(gstr3b_report.month_or_quarter, gstr3b_report.month)
        .run()
    )

    # Update company_gstin based on company_address
    docs = frappe.get_all(
        "GSTR 3B Report",
        fields=["name", "company_address", "company"],
    )

    for doc in docs:
        frappe.db.set_value(
            "GSTR 3B Report",
            doc.name,
            "company_gstin",
            get_gstin_based_on_address(doc),
        )


def get_gstin_based_on_address(doc):
    """Get GSTIN based on company_address or company"""
    gstin = frappe.db.get_value(
        "Address",
        filters={
            "name": doc.address_name,
        },
        fieldname="gstin",
    )

    if not gstin:
        gstin = gstin_list[0] if (gstin_list := get_gstin_list(doc.company)) else ""

    return gstin
