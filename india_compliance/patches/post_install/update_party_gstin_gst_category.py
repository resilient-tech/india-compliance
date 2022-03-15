import frappe
from frappe.contacts.doctype.address.address import (
    get_default_address,
    get_preferred_address,
)
from frappe.query_builder.functions import Count

custom_fields_to_delete = {
    "Company": ["pan_details"],
    "Customer": ["export_type"],
    "Supplier": ["export_type"],
}


def execute():
    update_pan_for_company()
    update_gstin_gst_category()
    delete_custom_fields()


def update_pan_for_company():
    # Updated pan_details with pan for consisitency in company
    company_pan = frappe.db.get_all(
        "Company", fields=["name", "pan_details"], filters={"pan_details": ["!=", ""]}
    )
    for company in company_pan:
        frappe.db.set_value(
            "Company", company.name, {"pan": company.pan_details, "pan_details": None}
        )


def update_gstin_gst_category():
    """
    Bulk Update gst category for overseas in address.
    Bulk Update: set use_party_gstin to False where there are more than one links.
    Set GSTIN in Party.
    Set GST Category in Address along with Use Party GSTIN as `0` for other address.
    """
    # bulk update gst category for overseas
    overseas_address = frappe.get_all(
        "Address",
        filters={
            "gstin": ("is", "not set"),
            "country": ("!=", "India"),
            "gst_category": ("is", "not set"),
        },
        fields=("name"),
    )

    if overseas_address:
        frappe.db.set_value(
            "Address",
            {"name": ("in", [addr.name for addr in overseas_address])},
            "gst_category",
            "Overseas",
        )

    # update use party gstin to zero `0` if links count is greater than 1
    links = frappe.qb.DocType("Dynamic Link")
    links_count = (
        frappe.qb.from_(links)
        .where(links.parenttype == "Address")
        .groupby(links.parent)
        .select(links.parent, Count(links.parent).as_("count"))
    ).run(as_dict=True)

    frappe.db.set_value(
        "Address",
        {"name": ("in", [link.parent for link in links_count if link.count > 1])},
        "use_party_gstin",
        0,
    )

    # update gstin in party
    for doctype in ("Customer", "Supplier", "Company"):
        for doc in frappe.get_all(doctype, fields=["name", "gstin", "gst_category"]):
            if doc.gstin:
                # in case user has custom gstin field in party
                update_address_for_party(doctype, doc, doc.gstin)
                continue

            default_address = get_default_address(doctype, doc.name)
            preferred_address = get_preferred_address(doctype, doc.name)

            if not default_address and not preferred_address:
                continue

            default_address = default_address or preferred_address
            default_gstin = frappe.db.get_value("Address", default_address, "gstin")
            frappe.db.set_value(doctype, doc.name, "gstin", default_gstin)

            # update gst category in address
            update_address_for_party(doctype, doc, default_gstin)


def update_address_for_party(doctype, doc, default_gstin):
    address_list = frappe.get_all(
        "Dynamic Link",
        filters={
            "parenttype": "Address",
            "link_doctype": doctype,
            "link_name": doc.name,
        },
        fields=("parent"),
    )

    for addr in address_list:
        addr_values = frappe.db.get_value(
            "Address", addr.parent, ["gstin", "gst_category", "use_party_gstin"]
        )
        if addr_values.gstin:
            if addr_values.gstin == default_gstin:
                frappe.db.set_value(
                    "Address", addr.parent, "gst_category", doc.gst_category
                )
            elif addr_values.gst_category == "Unregistered":
                frappe.db.set_value("Address", addr.parent, "gst_category", "")


def delete_custom_fields():
    for doctype, fields in custom_fields_to_delete.items():
        for field in fields:
            frappe.delete_doc("Custom Field", f"{doctype}-{field}")
