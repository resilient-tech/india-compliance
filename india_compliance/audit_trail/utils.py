import frappe
import frappe.defaults
from frappe import _


def is_audit_trail_enabled():
    return bool(frappe.db.get_single_value("Accounts Settings", "enable_audit_trail"))


@frappe.whitelist()
def get_audit_trail_doctypes(include_child: bool = False):
    doctypes = set(frappe.get_hooks("audit_trail_doctypes"))

    if not include_child:
        return doctypes

    child_doctypes = {
        df.options for doctype in doctypes for df in frappe.get_meta(doctype).get_table_fields()
    }

    return doctypes | child_doctypes


def is_audit_trail_enabled_for(doctype: str) -> bool:
    return is_audit_trail_enabled() and doctype in get_audit_trail_doctypes(include_child=True)


def throw_cannot_enable_ignore_versioning(doctype: str):
    frappe.throw(
        _(
            "Cannot enable Ignore Versioning for {0}, since versioning is required to maintain Audit Trail"
        ).format(frappe.bold(_(doctype))),
        title=_("Audit Trail"),
    )


def enqueue_disable_audit_trail_notification():
    frappe.enqueue(
        "india_compliance.audit_trail.utils.disable_audit_trail_notification",
        queue="short",
    )


@frappe.whitelist(methods=["POST"])
def disable_audit_trail_notification():
    frappe.defaults.clear_user_default("needs_audit_trail_notification")


@frappe.whitelist(methods=["POST"])
def enable_audit_trail():
    accounts_settings = frappe.get_doc("Accounts Settings")
    accounts_settings.enable_audit_trail = 1
    accounts_settings.save()
