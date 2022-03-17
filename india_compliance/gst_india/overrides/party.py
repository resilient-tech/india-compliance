import json

import frappe
from frappe import _

from india_compliance.gst_india.utils import validate_and_update_pan, validate_gstin


def validate_party(doc, method=None):
    doc.gstin = (doc.get("gstin") or "").upper().strip()
    validate_gstin(doc.gstin, doc.gst_category)
    validate_and_update_pan(doc)
    emit_docs_with_invalid_gstin(doc)


def emit_docs_with_invalid_gstin(doc, method=None):
    if not doc.has_value_changed("gstin"):
        return

    invalid_gstin = doc.get_doc_before_save().get("gstin") or ""
    if not invalid_gstin:
        return

    docs_with_invalid_gstin = get_docs_with_invalid_gstin(
        invalid_gstin, doc.doctype, doc.name
    )
    if not docs_with_invalid_gstin:
        return

    frappe.response.docs_with_invalid_gstin = {
        "invalid_gstin": invalid_gstin,
        "docs_with_invalid_gstin": docs_with_invalid_gstin,
    }


def get_docs_with_invalid_gstin(gstin, doctype, docname):
    docs_with_invalid_gstin = {}
    for dt in ("Address", "Supplier", "Customer"):
        for doc in frappe.get_all(dt, filters={"gstin": gstin}):
            if doc.name == docname and doctype == dt:
                continue

            docs_with_invalid_gstin.setdefault(dt, []).append(doc.name)

    return docs_with_invalid_gstin


@frappe.whitelist()
def update_docs_with_invalid_gstin(valid_gstin, gst_category, docs_with_invalid_gstin):
    docs_with_invalid_gstin = json.loads(docs_with_invalid_gstin)
    for doctype, docnames in docs_with_invalid_gstin.items():
        for docname in docnames:
            # TODO: Check permissions and update at all places where it is allowed
            doc = frappe.get_doc(doctype, docname)
            doc.gstin = valid_gstin
            doc.gst_category = gst_category
            doc.save()
