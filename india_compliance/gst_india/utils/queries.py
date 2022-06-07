import frappe


@frappe.whitelist()
def get_gstin_options(company):
    """
    This function does not check for permission because it only returns GSTINs,
    which are publicly accessible.
    """

    address = frappe.qb.DocType("Address")
    links = frappe.qb.DocType("Dynamic Link")

    addresses = (
        frappe.qb.from_(address)
        .inner_join(links)
        .on(address.name == links.parent)
        .select(address.gstin)
        .where(links.link_doctype == "Company")
        .where(links.link_name == company)
        .run(as_dict=1)
    )

    return list(set(d.gstin for d in addresses if d.gstin))
