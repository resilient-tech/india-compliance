import frappe
from frappe.query_builder.functions import IfNull

# Internal transfer / self-billing: company GSTIN == party GSTIN.
# These are already cleared of GST and excluded from returns; flag them so the
# new override is visible and consistent. Only invoices (not DN/PR, which can be
# legitimate same-GSTIN goods movements that still need an e-Waybill).
# (doctype, party_gstin_field)
TRANSACTIONS = [
    ("Sales Invoice", "billing_address_gstin"),
    ("Purchase Invoice", "supplier_gstin"),
]


def execute():
    indian_companies = frappe.get_all("Company", {"country": "India"}, pluck="name")
    if not indian_companies:
        return

    for doctype, party_field in TRANSACTIONS:
        doc = frappe.qb.DocType(doctype)
        (
            frappe.qb.update(doc)
            .set(doc.is_out_of_scope_of_gst, 1)
            .where(doc.company.isin(indian_companies))  # multi-company: only Indian companies
            .where(doc.docstatus == 1)  # submitted only; cancelled docs left as-is
            .where(IfNull(doc.company_gstin, "") != "")  # both-empty must not match
            .where(doc.company_gstin == doc[party_field])
            .where(IfNull(doc.is_out_of_scope_of_gst, 0) == 0)
        ).run()
