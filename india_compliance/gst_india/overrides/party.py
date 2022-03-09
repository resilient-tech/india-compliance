import json
from pydoc import doc
import frappe
from frappe import _

@frappe.whitelist()
def get_linked_addresses(party_type, party):
    addresses = frappe.get_all("Address", filters=[
        ["Dynamic Link", "link_doctype", "=", party_type],
        ["Dynamic Link", "link_name", "=", party],
        ["Dynamic Link", "parenttype", "=", "Address"],
        ["Address", "use_different_gstin", "=", 0]
    ], fields=['name', 'use_different_gstin'])

    multiple_address_to_update = []

    for address in addresses:
        if frappe.db.count("Dynamic Link", {'parent': address.name}) > 1:
            multiple_address_to_update.append(address.name)

    if multiple_address_to_update:
        return True, multiple_address_to_update
    else:
        return False, [address['name'] for address in addresses]

@frappe.whitelist()
def update_gstin(gstin, gst_category, addresses, update_all, multiple_address):
    if isinstance(addresses, str):
        addresses = json.loads(addresses)
    for data in addresses:
        addr_doc = frappe.get_doc("Address", data)
        addr_doc.gstin = gstin
        addr_doc.gst_category = gst_category

        # if not update_all and not doc.use_different_gstin and multiple_address:
        #     addr_doc.use_different_gstin = True

        if update_all and multiple_address:
            for link in addr_doc.links:
                frappe.db.set_value(link.link_doctype, link.link_name, {
                    'gstin': gstin,
                    'gst_category': gst_category
                })
            addr_doc.use_different_gstin = False
        addr_doc.save()
    return True
