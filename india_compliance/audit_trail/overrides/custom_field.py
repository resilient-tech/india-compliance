import frappe

from india_compliance.audit_trail.utils import (
    is_audit_trail_enabled_for,
    throw_cannot_enable_ignore_versioning,
)


def validate(doc, method=None):
    """
    `Ignore Versioning` cannot be enabled. An existing value is kept.
    """
    flags = frappe.local.flags

    if flags.in_install or flags.in_migrate:
        return

    if not doc.get("ignore_versioning") or not doc.has_value_changed("ignore_versioning"):
        return

    if not is_audit_trail_enabled_for(doc.dt):
        return

    throw_cannot_enable_ignore_versioning(doc.dt)
