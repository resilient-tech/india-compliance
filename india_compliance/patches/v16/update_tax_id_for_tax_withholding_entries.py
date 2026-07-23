import frappe
from frappe.query_builder import Bracket


def execute():
    """
    Update tax_id in Tax Withholding Entry from PAN of linked party (Customer/Supplier) for Indian companies.
    """
    indian_companies = frappe.get_all("Company", filters={"country": "India"}, pluck="name")
    if not indian_companies:
        return

    update_tax_id("Supplier", indian_companies)
    update_tax_id("Customer", indian_companies)


def update_tax_id(party_type, companies):
    twe = frappe.qb.DocType("Tax Withholding Entry")
    party = frappe.qb.DocType(party_type, alias="party")

    party_pan = frappe.qb.from_(party).select(party.pan).where(party.name == twe.party)
    parties_with_pan = (
        frappe.qb.from_(party).select(party.name).where(party.pan.isnotnull()).where(party.pan != "")
    )

    (
        frappe.qb.update(twe)
        .set(twe.tax_id, Bracket(party_pan))
        .where(twe.party_type == party_type)
        .where(twe.company.isin(companies))
        .where(twe.party.isin(parties_with_pan))
        .where(twe.created_by_migration == 0)
        .run()
    )
