import frappe


def execute():
    if not frappe.db.count("E Invoice User"):
        return

    for user in frappe.db.get_all("E Invoice User", fields=("name", "gstin")):
        company_name = frappe.db.sql(
            """
            SELECT dl.link_name FROM `tabAddress` a, `tabDynamic Link` dl
            WHERE a.gstin = %s AND dl.parent = a.name AND dl.link_doctype = 'Company'
        """,
            user.gstin,
        )
        if company_name and len(company_name) > 0:
            frappe.db.set_value(
                "E Invoice User", user.name, "company", company_name[0][0]
            )
