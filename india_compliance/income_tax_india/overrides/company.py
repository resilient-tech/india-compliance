import frappe

from ..setup import create_company_fixtures


def make_company_fixtures(doc, method=None):
    if not frappe.flags.country_change or doc.country != "India":
        return

    create_company_fixtures(doc.name)
