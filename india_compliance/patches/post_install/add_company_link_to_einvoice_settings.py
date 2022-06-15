import frappe


def execute():
    """
    update Company of E Invoice User from Dyanamic Link Table in Address
    """

    if not frappe.db.table_exists("E Invoice User"):
        return

    frappe.db.sql(
        """
        UPDATE `tabE Invoice User` user
        JOIN `tabAddress` address ON address.gstin = user.gstin
        JOIN `tabDynamic Link` dynamic_link
        ON dynamic_link.parent = address.name AND dynamic_link.link_doctype = 'Company'
        SET user.company = dynamic_link.link_name
        WHERE IFNULL(user.company, '') = ''
        """
    )

    # TODO: convert to query builder after fix of https://github.com/kayak/pypika/issues/675
    # user = frappe.qb.DocType("E Invoice User")
    # address = frappe.qb.DocType("Address")
    # dynamic_link = frappe.qb.DocType("Dynamic Link")
    # (
    #     frappe.qb.update(user)
    #     .join(address)
    #     .on(address.gstin == user.gstin)
    #     .join(dynamic_link)
    #     .on(
    #         (dynamic_link.parent == address.name)
    #         & (dynamic_link.link_doctype == "Company")
    #     )
    #     .set(user.company, dynamic_link.link_name)
    #     .where(IfNull(user.company, "") == "")
    #     .where(dynamic_link.link_doctype == "Company")
    #     .run()
    # )
