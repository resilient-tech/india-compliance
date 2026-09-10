import frappe
from frappe import _
from frappe.custom.doctype.customize_form.customize_form import (
    CustomizeForm as _CustomizeForm,
)

from india_compliance.audit_trail.utils import (
    get_audit_trail_doctypes,
    is_audit_trail_enabled,
    is_audit_trail_enabled_for,
)


class CustomizeForm(_CustomizeForm):
    @frappe.whitelist()
    def fetch_to_customize(self):
        self.set_onload(
            "audit_trail_enabled",
            bool(self.doc_type) and is_audit_trail_enabled_for(self.doc_type),
        )

        return super().fetch_to_customize()

    @frappe.whitelist()
    def save_customization(self):
        self.validate_audit_trail_integrity()
        return super().save_customization()

    def validate_audit_trail_integrity(self):
        if (
            not self.doc_type
            or self.track_changes
            or not is_audit_trail_enabled()
            or self.doc_type not in get_audit_trail_doctypes()
        ):
            return

        frappe.throw(
            _(
                "Cannot disable Track Changes for {0}, since it has been enabled to maintain Audit Trail"
            ).format(frappe.bold(_(self.doc_type))),
            title=_("Audit Trail"),
        )
