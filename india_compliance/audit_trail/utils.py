import frappe
import frappe.defaults
from frappe import _


def is_audit_trail_enabled():
    return bool(frappe.db.get_single_value("Accounts Settings", "enable_audit_trail"))


def get_audit_trail_doctypes(include_child: bool = False) -> set[str]:
    return set(iter_audit_trail_doctypes(include_child=include_child))


def iter_audit_trail_doctypes(include_child: bool = False):
    doctypes = set(frappe.get_hooks("audit_trail_doctypes"))
    yield from doctypes

    if not include_child:
        return

    for doctype in doctypes:
        yield from get_child_doctypes(doctype)


def get_child_doctypes(doctype: str):
    meta = frappe.get_meta(doctype)
    if meta.istable:
        return ()

    return meta._non_computed_table_doctypes.values()


def is_audit_trail_enabled_for(doctype: str) -> bool:
    if not is_audit_trail_enabled():
        return False

    # Check configured DocTypes before resolving their child tables
    return doctype in iter_audit_trail_doctypes(include_child=True)


def throw_cannot_enable_ignore_versioning(doctype: str):
    frappe.throw(
        _(
            "Cannot enable Ignore Versioning for fields in {0}, since versioning is required"
            " to maintain Audit Trail"
        ).format(frappe.bold(_(doctype))),
        title=_("Audit Trail Restriction"),
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
