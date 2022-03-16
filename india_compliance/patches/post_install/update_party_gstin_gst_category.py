import click

import frappe

custom_fields_to_delete = {
    "Company": ["pan_details"],
    "Customer": ["export_type"],
    "Supplier": ["export_type"],
}


def execute():
    update_pan_for_company()
    update_na_gstin()
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


def update_na_gstin():
    for doctype in ["Address", "Customer", "Supplier"]:
        docs = frappe.get_all(doctype, filters={"gstin": "NA"}, fields=["name"])
        if not docs:
            continue

        frappe.db.set_value(
            doctype, {"name": ("in", [doc.name for doc in docs])}, "gstin", ""
        )


def update_gstin_gst_category():
    """
    Bulk Update gst category for overseas in address.
    Set GSTIN in Party where there is same gstin across all address.
    Set GST Category in Address.
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

    # join Address and Party
    dynamic_links = frappe.qb.DocType("Dynamic Link")
    address = frappe.qb.DocType("Address")
    all_address_list = (
        frappe.qb.from_(address)
        .join(dynamic_links)
        .on(address.name == dynamic_links.parent)
        .where(dynamic_links.parenttype == "Address")
        .select(
            address.name,
            address.gstin,
            address.gst_category,
            dynamic_links.link_doctype,
            dynamic_links.link_name,
        )
        .run(as_dict=True)
    )

    print_warning = False
    for doctype in ("Customer", "Supplier", "Company"):
        for doc in frappe.get_all(doctype, fields=["name", "gstin", "gst_category"]):
            address_list = [
                addr
                for addr in all_address_list
                if addr.link_doctype == doctype and addr.link_name == doc.name
            ]
            if not address_list:
                continue

            if doc.gstin:
                # in case user has custom gstin field in party
                update_gst_category_for_address(doc, address_list, doc.gstin)
                continue

            # update gstin in party only where there is one gstin per party
            gstins = {addr.gstin for addr in address_list}
            if len(gstins) > 1:
                print_warning = True
                continue

            default_gstin = next(iter(gstins), None)
            frappe.db.set_value(doctype, doc.name, "gstin", default_gstin)
            update_gst_category_for_address(doc, address_list, default_gstin)

    if print_warning:
        click.secho(
            "We have identified multiple GSTINs for a few parties and couldnot set default GSTIN/GST Category there. "
            "Please check for parties without GSTINs or address without GST Category and set accordingly.",
            fg="yellow",
        )


def update_gst_category_for_address(doc, address_list, default_gstin):
    for addr in address_list:
        if addr.gstin != default_gstin:
            if addr.gstin and addr.gst_category == "Unregistered":
                frappe.db.set_value("Address", addr.name, {"gst_category": ""})
        else:
            frappe.db.set_value("Address", addr.name, "gst_category", doc.gst_category)


def delete_custom_fields():
    for doctype, fields in custom_fields_to_delete.items():
        for field in fields:
            frappe.delete_doc("Custom Field", f"{doctype}-{field}")
