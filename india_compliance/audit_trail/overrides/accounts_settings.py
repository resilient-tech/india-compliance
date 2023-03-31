import frappe
from frappe import _

from india_compliance.audit_trail.setup import create_property_setters_for_versioning


def validate(doc, method=None):
    validate_change_in_enable_audit_trail(doc)
    validate_delete_linked_ledger_entries(doc)


def validate_change_in_enable_audit_trail(doc):
    if not doc.has_value_changed("enable_audit_trail"):
        return

    if not doc.enable_audit_trail:
        frappe.throw(_("Audit Trail cannot be disabled once enabled"))

    # Enable audit trail
    doc.delete_linked_ledger_entries = 0
    frappe.enqueue(create_property_setters_for_versioning, queue="short", at_front=True)


def validate_delete_linked_ledger_entries(doc):
    if doc.enable_audit_trail and doc.delete_linked_ledger_entries:
        frappe.throw(
            _("{0} cannot be enabled to ensure Audit Trail integrity").format(
                frappe.bold(doc.meta.get_label("delete_linked_ledger_entries"))
            )
        )
