frappe.ui.form.on("Purchase Invoice", {
    refresh(frm) {
        if (
            frm.doc.docstatus !== 1 ||
            frm.doc.gst_category !== "Overseas" ||
            frm.doc.__onload?.bill_of_entry_exists
        )
            return;

        frm.add_custom_button(
            __("Bill of Entry"),
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
