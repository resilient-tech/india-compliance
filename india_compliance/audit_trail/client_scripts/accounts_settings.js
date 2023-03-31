frappe.ui.form.on("Accounts Settings", {
    refresh(frm) {
        if (!frm.doc.enable_audit_trail) return;

        frm.set_df_property("enable_audit_trail", "read_only", 1);

        // this should never happen, but just in case
        if (frm.doc.delete_linked_ledger_entries) {
            frm.set_value("delete_linked_ledger_entries", 0);
        }

        toggle_linked_ledger_entry_deletion(frm);
    },
    enable_audit_trail(frm) {
        toggle_linked_ledger_entry_deletion(frm);

        if (frm.doc.enable_audit_trail && frm.doc.delete_linked_ledger_entries) {
            frappe.msgprint({
                title: __("Warning"),
                indicator: "orange",
                message: __(
                    "<strong>{0}</strong> will be disabled to ensure Audit Trail integrity",
                    [
                        __(
                            frappe.meta.get_label(
                                "Accounts Settings",
                                "delete_linked_ledger_entries",
                                frm.doc.name
                            )
                        ),
                    ]
                ),
            });
            frm.set_value("delete_linked_ledger_entries", 0);
        }
    },
    after_save(frm) {
        if (frm.doc.enable_audit_trail) {
            frappe.boot.audit_trail_enabled = true;
        }
    }
});

function toggle_linked_ledger_entry_deletion(frm) {
    frm.set_df_property(
        "delete_linked_ledger_entries",
        "read_only",
        frm.doc.enable_audit_trail
    );
    frm.set_df_property(
        "delete_linked_ledger_entries",
        "description",
        frm.doc.enable_audit_trail
            ? "This setting has been disabled to ensure Audit Trail integrity."
            : ""
    );
}
