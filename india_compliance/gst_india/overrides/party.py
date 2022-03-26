import json

import frappe
from frappe import _, bold

from india_compliance.gst_india.utils import is_valid_pan, validate_gstin


def validate_party(doc, method=None):
    validate_pan_and_gstin(doc, called_from_ui=False)
    set_docs_with_previous_gstin(doc)


@frappe.whitelist()
def validate_pan_and_gstin(doc, called_from_ui=True):
    if called_from_ui:
        doc = frappe.parse_json(doc)

    doc.gstin = validate_gstin(doc.gstin, doc.gst_category)
    doc.pan = validate_pan(doc)

    if called_from_ui:
        frappe.response.docs.append(doc)


@frappe.whitelist()
def validate_pan(doc):
    """
    - Set PAN from GSTIN if available.
    - Validate PAN.
    """
    pan = doc.pan and doc.pan.upper().strip()
    if doc.gstin:
        pan = pan_from_gstin if is_valid_pan(pan_from_gstin := doc.gstin[2:12]) else ""

    elif pan and not is_valid_pan(pan):
        frappe.throw(_("Please check the PAN."), title=_("Invalid PAN"))

    return pan


def set_docs_with_previous_gstin(doc, method=True):
    if not frappe.request or frappe.flags.dont_set_docs_with_previous_gstin:
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
    for dt in ("Address", "Supplier", "Customer"):
        for doc in frappe.get_all(dt, filters={"gstin": gstin}):
            if doc.name == docname and doctype == dt:
                continue

            docs_with_previous_gstin.setdefault(dt, []).append(doc.name)

    return docs_with_previous_gstin


@frappe.whitelist()
def update_docs_with_previous_gstin(gstin, gst_category, docs_with_previous_gstin):
    frappe.flags.dont_set_docs_with_previous_gstin = True
    docs_with_previous_gstin = json.loads(docs_with_previous_gstin)
    ignored_docs = {}
    for doctype, docnames in docs_with_previous_gstin.items():
        for docname in docnames:
            try:
                doc = frappe.get_doc(doctype, docname)
                doc.gstin = gstin
                doc.gst_category = gst_category
                doc.save()
            except frappe.PermissionError:
                frappe.clear_last_message()
                ignored_docs.setdefault(doctype, []).append(docname)
            except Exception:
                # TODO: handle this in better way
                pass

    if not ignored_docs:
        return frappe.msgprint(
            _("Updated GSTIN in all documents"), indicator="green", alert=True
        )

    message = _(
        "Following documents are not updated due to lack of Permission:<br/><br/>"
    )
    for doctype, docnames in ignored_docs.items():
        if not docnames:
            continue

        message += f"{bold(doctype)}:<br/>{'<br/>'.join(docnames)}"

    frappe.msgprint(message, title=_("Insufficient Permission"), indicator="yellow")
