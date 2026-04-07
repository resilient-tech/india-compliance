import frappe


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
    twe = frappe.qb.DocType("Tax Withholding Entry", alias="twe")
    party = frappe.qb.DocType(party_type, alias="party")

    (
        frappe.qb.update(twe)
        .join(party)
        .on(twe.party == party.name)
        .set(twe.tax_id, party.pan)
        .where(twe.party_type == party_type)
        .where(twe.company.isin(companies))
        .where(party.pan.isnotnull())
        .where(party.pan != "")
        .where(twe.created_by_migration == 0)
        .run()
    )
