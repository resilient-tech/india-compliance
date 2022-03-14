import frappe
from frappe.contacts.doctype.address.address import (
    get_default_address,
    get_preferred_address,
)

# Ensure that you update use_gstin to address where different GSTIN may be needed.


# Set PAN and GST Transporter ID from GSTIN. Improve GSTIN Validation.
# Fetch from Billing Address if available or Party in all transactions.
# Get default export type from GST Settings in Sales Transactions.

#
# Remove Export Type from Party.
# Make default Export Type from GST Settings. Remove this field from Party Details.
# Improve GSTIN Validation.


def execute():
    update_pan_for_company()
    addresses = frappe.db.get_all(
        "Address", fields=["name", "country", "gst_category", "gstin"]
    )
    if addresses:
        # If country is not India in Address, set gst category Overseas
        frappe.db.set_value(
            "Address",
            {
                "name": [
                    "in",
                    [
                        address.name
                        for address in addresses
                        if address.country != "India"
                        and address.gst_category != "Overseas"
                    ],
                ]
            },
            "gst_category",
            "Overseas",
        )

        # If gstin is not available, gst category will be set as Unregistered
        frappe.db.set_value(
            "Address",
            {
                "name": [
                    "in",
                    [
                        address.name
                        for address in addresses
                        if not address.gstin or address.gstin == "URP"
                    ],
                ]
            },
            "gst_category",
            "Unregistered",
        )

        # Set GSTIN as per party in address
        for address in addresses:
            if not address.gstin or address.gstin == "URP":
                linked_party = frappe.db.get_value(
                    "Dynamic Link",
                    {
                        "parent": address.name,
                        "link_doctype": ["in", ["Customer", "Supplier", "Company"]],
                    },
                    ["link_doctype", "link_name"],
                    as_dict=True,
                )

                if linked_party:
                    party_gstin = frappe.db.get_value(
                        linked_party.link_doctype, linked_party.link_name, "gstin"
                    )

                    if party_gstin:
                        frappe.db.set_value(
                            "Address", address.name, "gstin", party_gstin
                        )

    # Set GSTIN in party from their default or primary address
    for doctype in ["Customer", "Supplier"]:
        docs = frappe.db.get_all(doctype, filters={"gstin": ["=", ""]}, fields=["name"])
        for doc in docs:
            default_address = get_default_address(doctype, doc.name)
            preferred_address = get_preferred_address(doctype, doc.name)
            address_gstin = frappe.db.get_value(
                "Address",
                {"name": ["in", [default_address, preferred_address]]},
                "gstin",
            )
            frappe.db.set_value(doctype, doc.name, "gstin", address_gstin)


# Updated pan_details with pan for consisitency
def update_pan_for_company():
    company_pan = frappe.db.get_all(
        "Company", fields=["name", "pan_details"], filters={"pan_details": ["!=", ""]}
    )
    for company in company_pan:
        frappe.db.set_value(
            "Company", company.name, {"pan": company.pan_details, "pan_details": None}
        )
