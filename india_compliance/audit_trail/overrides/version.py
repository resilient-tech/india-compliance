import frappe
from frappe import _

from india_compliance.audit_trail.utils import (
    get_audit_trail_doctypes,
    is_audit_trail_enabled,
)


def validate(doc, method=None):
    if doc.is_new() or not is_audit_trail_enabled():
        return

    validate_protected_version(doc)
    if old_doc := doc.get_doc_before_save():
        validate_protected_version(old_doc)


def on_trash(doc, method=None):
    if not is_audit_trail_enabled():
        return

    validate_protected_version(doc)


def validate_protected_version(doc):
    if doc.ref_doctype in get_audit_trail_doctypes():
        frappe.throw(
            _(
                "Cannot alter Versions of {0}, since they are required for Audit Trail"
            ).format(_(doc.ref_doctype))
        )
