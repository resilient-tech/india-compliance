import json
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

    print(addresses)

    multiple_address_to_update = []

    for address in addresses:
        if frappe.db.count("Dynamic Link", {'parent': address.name}) > 1:
            multiple_address_to_update.append(address.name)

    print(multiple_address_to_update)
    if multiple_address_to_update:
        return True, multiple_address_to_update
    else:
        return False, [address['name'] for address in addresses]

def update_gstin_in_linked_address(doc, method):
    print(doc.doctype)
    cache_doc = frappe.get_cached_doc(doc.doctype, doc.name)
    print(cache_doc.gstin)
    print(doc.gstin)
    if doc.gstin != cache_doc.gstin:
        addresses = frappe.get_all("Address", filters=[
            ["Dynamic Link", "link_doctype", "=", doc.doctype],
            ["Dynamic Link", "link_name", "=", doc.name],
            ["Dynamic Link", "parenttype", "=", "Address"]
        ], fields=['name', 'use_different_gstin'])

        print(addresses)

        multiple_address_to_update = []

        for address in addresses:
            if frappe.db.count("Dynamic Link", {'parent': address.name}) > 1:
                multiple_address_to_update.append(address.name)

        print(multiple_address_to_update)
            
        if multiple_address_to_update:
            frappe.msgprint(
                msg=frappe._(f'We shall update {multiple_address_to_update} all linked records also, Proceed?'),
                title='Confirm Update',
                primary_action={
                    'label': frappe._('Yes, Proceed'),
                    'server_action': 'india_compliance.gst_india.overrides.party.update_gstin',
                    'args': {
                        'addresses': multiple_address_to_update,
                        'gstin': doc.gstin,
                        'gst_category': doc.gst_category
                    }
                }
            )
        else:
            update_gstin(args={'addresses': [address['name'] for address in addresses], 'gstin': doc.gstin, 'gst_category': doc.gst_category})

@frappe.whitelist()
def update_gstin(gstin, gst_category, addresses, update_all):
    if isinstance(addresses, str):
        addresses = json.loads(addresses)
    for data in addresses:
        addr_doc = frappe.get_doc("Address", data)
        addr_doc.gstin = gstin
        addr_doc.gst_category = gst_category
        if update_all:
            for link in addr_doc.links:
                frappe.db.set_value(link.link_doctype, link.link_name, {
                    'gstin': gstin,
                    'gst_category': gst_category
                })
        else:
            addr_doc.use_different_gstin = True
        addr_doc.save()
    return True
