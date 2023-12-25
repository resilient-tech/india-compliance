import json

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
    # Any transaction can be treated as deemed export
    if doc.gstin and doc.gst_category == "Deemed Export":
        return "Deemed Export"

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
        }
    ).insert()
