import frappe
from frappe.query_builder.functions import IfNull

from india_compliance.utils.custom_fields import delete_old_fields


def execute():
    if not frappe.db.has_column("Company", "logo_for_printing"):
        return

    company = frappe.qb.DocType("Company")

    (
        frappe.qb.update(company)
        .set(company.company_logo, company.logo_for_printing)
        .where(IfNull(company.logo_for_printing, "") != "")
        .where(IfNull(company.company_logo, "") == "")
        .run()
    )

    delete_old_fields("logo_for_printing", "Company")
