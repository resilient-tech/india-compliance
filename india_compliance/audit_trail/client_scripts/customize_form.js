frappe.ui.form.on("Customize Form", {
    refresh: function (frm) {
        const audit_trail_enabled = frm.doc.doc_type && frm.doc.__onload?.audit_trail_enabled;

        // this should never happen, but just in case. `track_changes` is not used by child tables
        if (audit_trail_enabled && !frm.doc.istable && !frm.doc.track_changes) {
            frm.set_value("track_changes", 1);
        }

        frm.set_df_property("track_changes", "read_only", audit_trail_enabled);
        frm.set_df_property(
            "track_changes",
            "description",
            audit_trail_enabled ? __("This setting cannot be edited to ensure Audit Trail integrity.") : "",
        );

        toggle_ignore_versioning(frm, audit_trail_enabled);
    },
});

function toggle_ignore_versioning(frm, audit_trail_enabled) {
    // Form Builder skips hidden docfields
    const df = frappe.meta.get_docfield("Customize Form Field", "ignore_versioning");
    if (!df) return;

    df.hidden = audit_trail_enabled ? 1 : 0;

    // the fields table has its own copy of the docfield
    frm.fields_dict.fields?.grid?.toggle_display("ignore_versioning", !audit_trail_enabled);
}
