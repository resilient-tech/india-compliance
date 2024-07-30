import json
import random

import requests

import frappe
from frappe import _
from frappe.contacts.doctype.address.address import get_address_display

from india_compliance.gst_india.utils import (
    guess_gst_category,
    is_autofill_party_info_enabled,
    is_valid_pan,
    validate_gst_category,
    validate_gstin,
)
from india_compliance.gst_india.utils.gstin_info import _get_gstin_info


def validate_party(doc, method=None):
    doc.gstin = validate_gstin(doc.gstin)
    set_gst_category(doc)
    validate_gst_category(doc.gst_category, doc.gstin)
    validate_pan(doc)
    set_docs_with_previous_gstin(doc)


def set_gst_category(doc):
    """
    Set GST Category from GSTIN.
    """
    gst_category = fetch_or_guess_gst_category(doc)

    if doc.gst_category == gst_category:
        return

    doc.gst_category = gst_category

    frappe.msgprint(
        _("GST Category updated to {0}.").format(frappe.bold(gst_category)),
        indicator="green",
        alert=True,
    )


def fetch_or_guess_gst_category(doc):
    # High Seas Sales
    if doc.gst_category == "Overseas":
        return doc.gst_category

    # Any transaction can be treated as deemed export
    if doc.gstin and doc.gst_category == "Deemed Export":
        return doc.gst_category

    if doc.gstin and is_autofill_party_info_enabled():
        gstin_info = _get_gstin_info(doc.gstin, throw_error=False) or {}

        if gstin_info.get("gst_category"):
            return gstin_info.gst_category

    return guess_gst_category(doc.gstin, doc.get("country"), doc.gst_category)


def validate_pan(doc):
    """
    - Set PAN from GSTIN if available.
    - Validate PAN.
    """

    if doc.gstin:
        doc.pan = (
            pan_from_gstin if is_valid_pan(pan_from_gstin := doc.gstin[2:12]) else ""
        )
        return

    if not doc.pan:
        return

    doc.pan = doc.pan.upper().strip()
    if not is_valid_pan(doc.pan):
        frappe.throw(_("Invalid PAN format"))


def set_docs_with_previous_gstin(doc, method=None):
    if not frappe.request or frappe.flags.in_update_docs_with_previous_gstin:
        return

    previous_gstin = (doc.get_doc_before_save() or {}).get("gstin")
    if not previous_gstin or previous_gstin == doc.gstin:
        return

    docs_with_previous_gstin = get_docs_with_previous_gstin(
        previous_gstin, doc.doctype, doc.name
    )
    if not docs_with_previous_gstin:
        return

    frappe.response.docs_with_previous_gstin = docs_with_previous_gstin
    frappe.response.previous_gstin = previous_gstin


def get_docs_with_previous_gstin(gstin, doctype, docname):
    docs_with_previous_gstin = {}
    for dt in ("Address", "Supplier", "Customer", "Company"):
        for doc in frappe.get_list(dt, filters={"gstin": gstin}):
            if doc.name == docname and doctype == dt:
                continue

            docs_with_previous_gstin.setdefault(dt, []).append(doc.name)

    return docs_with_previous_gstin


@frappe.whitelist()
def update_docs_with_previous_gstin(gstin, gst_category, docs_with_previous_gstin):
    frappe.flags.in_update_docs_with_previous_gstin = True
    docs_with_previous_gstin = json.loads(docs_with_previous_gstin)

    for doctype, docnames in docs_with_previous_gstin.items():
        for docname in docnames:
            try:
                doc = frappe.get_doc(doctype, docname)
                doc.gstin = gstin
                doc.gst_category = gst_category
                doc.save()
            except Exception as e:
                frappe.clear_last_message()
                frappe.throw(
                    "Error updating {0} {1}:<br/> {2}".format(doctype, docname, str(e))
                )

    frappe.msgprint(_("GSTIN Updated"), indicator="green", alert=True)


def create_primary_address(doc, method=None):
    """
    Used to create primary address when creating party.
    Modified version of erpnext.selling.doctype.customer.customer.create_primary_address

    ERPNext uses `address_line1` so we use `_address_line1` to avoid conflict.
    """
    if not doc.get("_address_line1"):
        return

    address = make_address(doc)
    address_display = get_address_display(address.as_dict())

    doc.db_set(f"{doc.doctype.lower()}_primary_address", address.name)
    doc.db_set("primary_address", address_display)


def make_address(doc):
    return frappe.get_doc(
        {
            "doctype": "Address",
            "address_title": doc.name,
            "address_line1": doc.get("_address_line1"),
            "address_line2": doc.get("address_line2"),
            "city": doc.get("city"),
            "state": doc.get("state"),
            "pincode": doc.get("pincode"),
            "country": doc.get("country"),
            "gstin": doc.gstin,
            "gst_category": doc.gst_category,
            "links": [{"link_doctype": doc.doctype, "link_name": doc.name}],
            "is_primary_address": doc.get("is_primary_address"),
            "is_shipping_address": doc.get("is_shipping_address"),
        }
    ).insert()


multiplication_table = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
    [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
    [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
    [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
    [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]

permutation_table = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
    [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
    [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
    [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]

inverse_table = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]


def verhoeff_checksum(number: str) -> int:
    """Calculate the Verhoeff checksum digit."""
    c = 0
    n = len(number)
    for i in range(n):
        c = multiplication_table[c][
            permutation_table[(i + 1) % 8][int(number[n - i - 1])]
        ]
    return inverse_table[c]


def generate_aadhaar_number():
    """Generate a valid Aadhaar number using the Verhoeff algorithm."""
    base_number = "".join([str(random.randint(0, 9)) for _ in range(11)])
    check_digit = verhoeff_checksum(base_number)
    return base_number + str(check_digit)


@frappe.whitelist()
def validate_pancard_status(pan):
    aadhaar_number = generate_aadhaar_number()
    url = "https://eportal.incometax.gov.in/iec/servicesapi/getEntity"
    payload = {
        "aadhaarNumber": aadhaar_number,
        "pan": pan,
        "preLoginFlag": "Y",
        "serviceName": "linkAadhaarPreLoginService",
    }
    response = requests.post(url, json=payload)
    messages = response.json().get("messages", [])

    if messages and "linked to some other Aadhaar" in messages[0].get("desc", ""):
        return "Linked"
    elif messages and "PAN does not exist." in messages[0].get("desc", ""):
        return "Invalid PAN"
    elif messages and "Individual taxpayers" in messages[0].get("desc", ""):
        return "Not an Individual Taxpayer"
    return ""
