import click

import frappe


def execute():
    update_pan_for_company()
    update_na_gstin()
    update_gstin_gst_category()
    delete_custom_fields()


def update_pan_for_company():
    # Updated pan_details with pan for consisitency in company
    if not frappe.db.has_column("Company", "pan_details"):
        return

    company = frappe.qb.DocType("Company")
    frappe.qb.update(company).set(company.pan, company.pan_details).where(
        company.pan_details != ""
    ).run()


def update_na_gstin():
    for doctype in {"Address", "Customer", "Supplier"}:
        frappe.db.set_value(doctype, {"gstin": "NA"}, "gstin", None)


def update_gstin_gst_category():
    """
    Bulk Update gst category for overseas in address.
    Set GSTIN in Party where there is same gstin across all address.
    Set GST Category in Address.
    """
    # bulk update gst category for overseas
    frappe.db.set_value(
        "Address",
        {"gst_category": "", "gstin": "", "country": ("!=", "India")},
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

    # group by doctype, docname
    address_map = {}
    for address in all_address_list:
        address_map.setdefault((address.link_doctype, address.link_name), []).append(
            address
        )

    new_gstins = {}
    new_gst_categories = {}
    print_warning = False
    for doctype in ("Customer", "Supplier", "Company"):
        for doc in frappe.get_all(doctype, fields=("name", "gstin", "gst_category")):
            address_list = address_map.get((doctype, doc.name))
            if not address_list:
                continue

            # in case user has custom gstin field in party
            default_gstin = doc.gstin
            if not doc.gstin:
                # update gstin in party only where there is one gstin per party
                gstins = {addr.gstin for addr in address_list}
                if len(gstins) > 1:
                    print_warning = True
                    continue

                default_gstin = next(iter(gstins), None)
                new_gstins.setdefault((doctype, default_gstin), []).append(doc.name)

            for address in address_list:
                gst_category = doc.gst_category
                if (
                    address.gstin
                    and address.gstin != default_gstin
                    and address.gst_category == "Unregistered"
                ):
                    gst_category = ""

                new_gst_categories.setdefault((doctype, gst_category), []).append(
                    doc.name
                )

    for (doctype, gstin), docnames in new_gstins.items():
        frappe.db.set_value(doctype, {"name": ("in", docnames)}, "gstin", gstin)

    for (doctype, gst_category), docnames in new_gst_categories.items():
        frappe.db.set_value(
            doctype, {"name": ("in", docnames)}, "gst_category", gst_category
        )

    if print_warning:
        click.secho(
            "We have identified multiple GSTINs for a few parties and couldnot set"
            " default GSTIN/GST Category there. Please check for parties without GSTINs"
            " or address without GST Category and set accordingly.",
            fg="yellow",
        )


def delete_custom_fields():
    for doctype, fields in {
        "Company": ("pan_details",),
        "Customer": ("export_type",),
        "Supplier": ("export_type",),
    }.items():
        frappe.db.delete("Custom Field", {"dt": doctype, "fieldname": ("in", fields)})
