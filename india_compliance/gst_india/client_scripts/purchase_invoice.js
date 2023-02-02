frappe.ui.form.on("Purchase Invoice", {
    refresh(frm) {
        if (
            frm.doc.docstatus != 1 ||
            frm.doc.gst_category != "Overseas" ||
            frm.doc.__onload?.existing_bill_of_entry
        )
            return;

        frm.add_custom_button(
            __("Create Bill of Entry"),
            () => {
                frappe.model.open_mapped_doc({
                    method: "india_compliance.gst_india.doctype.bill_of_entry.bill_of_entry.make_bill_of_entry",
                    frm: frm,
                });
            },
            __("Create")
        );
    },
});
