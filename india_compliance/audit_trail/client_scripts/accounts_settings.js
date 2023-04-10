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
        if (!frm.doc.enable_audit_trail) return;

        let message = __("Audit Trail cannot be disabled once enabled.");
        if (frm.doc.delete_linked_ledger_entries) {
            message += __(
                `<br><br>
                Additionally, the following setting will be disabled
                to ensure Audit Trail integrity:<br>
                <strong>{0}</strong>`,
                [
                    __(
                        frappe.meta.get_label(
                            "Accounts Settings",
                            "delete_linked_ledger_entries",
                            frm.doc.name
                        )
                    ),
                ]
            );
            frm.set_value("delete_linked_ledger_entries", 0);
        }

        frappe.msgprint({
            title: __("Warning"),
            indicator: "orange",
            message,
        });
    },
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
