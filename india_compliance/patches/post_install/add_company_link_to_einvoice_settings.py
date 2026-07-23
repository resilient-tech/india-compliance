import frappe
from frappe.query_builder import Bracket
from frappe.query_builder.functions import IfNull


def execute():
    """
    update Company of E Invoice User from Dyanamic Link Table in Address
    """

    if not frappe.db.table_exists("E Invoice User"):
        return

    user = frappe.qb.DocType("E Invoice User")
    address = frappe.qb.DocType("Address", alias="address")
    dynamic_link = frappe.qb.DocType("Dynamic Link", alias="dynamic_link")
    linked_company = (
        frappe.qb.from_(address)
        .join(dynamic_link)
        .on((dynamic_link.parent == address.name) & (dynamic_link.link_doctype == "Company"))
        .select(dynamic_link.link_name)
        .where(address.gstin == user.gstin)
        .orderby(dynamic_link.link_name)
        .limit(1)
    )
    linked_gstins = (
        frappe.qb.from_(address)
        .join(dynamic_link)
        .on((dynamic_link.parent == address.name) & (dynamic_link.link_doctype == "Company"))
        .select(address.gstin)
    )

    (
        frappe.qb.update(user)
        .set(user.company, Bracket(linked_company))
        .where(IfNull(user.company, "") == "")
        .where(user.gstin.isin(linked_gstins))
        .run()
    )
