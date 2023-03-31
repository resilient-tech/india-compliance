import frappe
from frappe import _
from frappe.utils import cint

from india_compliance.audit_trail.utils import (
    get_audit_trail_doctypes,
    is_audit_trail_enabled,
)


def validate(doc, method=None):
    if (
        frappe.flags.in_install
        or frappe.flags.in_migrate
        or not is_audit_trail_enabled()
    ):
        return

    is_protected = is_protected_property_setter(doc)
    if doc.is_new() and (not is_protected or cint(doc.value) == 1):
        return

    if is_protected:
        throw_cannot_change_property_error(doc)

    old_doc = doc.get_doc_before_save()
    if is_protected_property_setter(old_doc):
        throw_cannot_change_property_error(old_doc)


def on_trash(doc, method=None):
    if not is_audit_trail_enabled() or not is_protected_property_setter(doc):
        return

    throw_cannot_change_property_error(doc)


def throw_cannot_change_property_error(doc):
    frappe.throw(
        _(
            "Cannot change the Track Changes property for {0}, since it has been"
            " enabled to maintain Audit Trail"
        ).format(_(doc.doc_type))
    )


def is_protected_property_setter(doc):
    return (
        doc.doctype_or_field == "DocType"
        and doc.property == "track_changes"
        and doc.doc_type in get_audit_trail_doctypes()
    )
