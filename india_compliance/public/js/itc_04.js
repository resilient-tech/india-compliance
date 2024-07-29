frappe.provide("india_compliance");

india_compliance.render_data_table = (ref_doc_btn, frm, field, data) => {
    ref_doc_btn.data = data;

    var dialog = new frappe.ui.Dialog({
        title: __("Select Original Document Reference"),
        fields: [
            {
                fieldtype: "HTML",
                fieldname: "doc_references_data",
            },
        ],
        primary_action_label: __("Fetch"),
        primary_action: function () {
            let checked_rows_indexes =
                ref_doc_btn.datatable.rowmanager.getCheckedRows();

            if (checked_rows_indexes.length) {
                let checked_rows = checked_rows_indexes.map(i => ref_doc_btn.data[i]);
                checked_rows.forEach(docs => {
                    var row = cur_frm.add_child(field);
                    row.link_doctype = docs.Doctype;
                    row.link_name = docs.Name;
                });
                frm.refresh_field(field);
                dialog.hide();
            } else {
                frappe.msgprint(__("Please select at least one row."));
            }
        },
    });

    setTimeout(function () {
        ref_doc_btn.datatable = new frappe.DataTable(
            dialog.get_field("doc_references_data").wrapper,
            {
                columns: ["Doctype", "Name"],
                data: ref_doc_btn.data,
                layout: "fluid",
                serialNoColumn: false,
                checkboxColumn: true,
                inlineFilters: true,
                cellHeight: 35,
            }
        );
    }, 200);

    dialog.show();
};
