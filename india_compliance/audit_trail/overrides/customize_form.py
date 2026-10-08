import frappe
from frappe import _
from frappe.custom.doctype.customize_form.customize_form import (
    CustomizeForm as _CustomizeForm,
)

from india_compliance.audit_trail.utils import (
    get_audit_trail_doctypes,
    is_audit_trail_enabled,
    is_audit_trail_enabled_for,
    throw_cannot_enable_ignore_versioning,
)


class CustomizeForm(_CustomizeForm):
    @frappe.whitelist()
    def fetch_to_customize(self):
        self.set_onload(
            "audit_trail_enabled",
            self.doc_type and is_audit_trail_enabled_for(self.doc_type),
        )

        return super().fetch_to_customize()

    @frappe.whitelist()
    def save_customization(self):
        self.validate_audit_trail_integrity()
        self.validate_ignore_versioning()
        return super().save_customization()

    def validate_ignore_versioning(self):
        """
        Custom Fields are updated with `db_update`, which skips their validation,
        so the fields have to be checked here.
        """
        if not self.doc_type or not is_audit_trail_enabled_for(self.doc_type):
            return

        meta = frappe.get_meta(self.doc_type)
        for df in self.get("fields"):
            if not df.get("ignore_versioning"):
                continue

            # an existing value is left as it is, only turning it on is refused
            meta_df = meta.get_field(df.fieldname)
            if not meta_df or not meta_df.get("ignore_versioning"):
                throw_cannot_enable_ignore_versioning(self.doc_type)

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
            title=_("Audit Trail Restriction"),
        )
