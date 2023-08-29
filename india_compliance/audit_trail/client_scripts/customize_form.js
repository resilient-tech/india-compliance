frappe.ui.form.on("Customize Form", {
    refresh: function (frm) {
        const audit_trail_enabled =
            frm.doc.doc_type && frm.doc.__onload?.audit_trail_enabled;

        // this should never happen, but just in case
        if (audit_trail_enabled && !frm.doc.track_changes) {
            frm.set_value("track_changes", 1);
        }

        frm.set_df_property("track_changes", "read_only", audit_trail_enabled);
        frm.set_df_property(
            "track_changes",
            "description",
            audit_trail_enabled
                ? __("This setting cannot be edited to ensure Audit Trail integrity.")
                : ""
        );
    },
});
