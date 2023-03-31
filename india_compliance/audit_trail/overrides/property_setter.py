import frappe
from frappe import _

from india_compliance.audit_trail.utils import (
    get_audit_trail_doctypes,
    is_audit_trail_enabled,
)


def validate(doc, method=None):
    if (
        not is_audit_trail_enabled()
        or doc.flags.for_audit_trail
        or frappe.flags.in_install
        or frappe.flags.in_migrate
    ):
        return

    validate_protected_property_setter(doc)
    if old_doc := doc.get_doc_before_save():
        validate_protected_property_setter(old_doc)


def on_trash(doc, method=None):
    if not is_audit_trail_enabled():
        return

    validate_protected_property_setter(doc)


def validate_protected_property_setter(doc):
    if (
        doc.doctype_or_field == "DocType"
        and doc.property == "track_changes"
        and doc.doc_type in get_audit_trail_doctypes()
    ):
        frappe.throw(
            _(
                "Cannot change the Track Changes property for {0}, since it has been"
                " enabled to maintain Audit Trail"
            ).format(_(doc.doc_type))
        )
