{% include "india_compliance/gst_india/client_scripts/party.js" %}

const DOCTYPE = "Company";

validate_pan(DOCTYPE);
validate_gstin(DOCTYPE);
update_gstin_in_other_documents(DOCTYPE);
show_overseas_disabled_warning(DOCTYPE);
set_gstin_options_and_status(DOCTYPE);
set_pan_status(DOCTYPE)

frappe.ui.form.off(DOCTYPE, "make_default_tax_template");
frappe.ui.form.on(DOCTYPE, {
    refresh(frm){
        frm.fields_dict.bank_details_for_printing.grid.fields_map.print_label.ignore_validation = 1
        frm.fields_dict.registration_details_for_printing.grid.fields_map.print_label.ignore_validation = 1
    },
    setup(frm) {
        erpnext.company.set_custom_query(frm, [
            "default_customs_expense_account",
            { root_type: "Expense" },
        ]);
        erpnext.company.set_custom_query(frm, [
            "default_customs_payable_account",
            { root_type: "Liability" },
        ]);

        frm.set_query("print_label", "bank_details_for_printing", (_, cdt, cdn) => {
            return  {
                query: "india_compliance.gst_india.overrides.company.get_default_print_options",
                params : {for_bank : 1}
            }
        });
        frm.set_query("print_label", "registration_details_for_printing", (_, cdt, cdn) => {
            return {
                query: "india_compliance.gst_india.overrides.company.get_default_print_options",
                params : {for_bank : 0}
            }
        });
    },

    make_default_tax_template: function (frm) {
        if (frm.doc.country !== "India") return;

        frappe.call({
            method: "india_compliance.gst_india.overrides.company.make_default_tax_templates",
            args: { company: frm.doc.name, gst_rate: frm.doc.default_gst_rate},
            callback: function () {
                frappe.msgprint(__("Default Tax Templates created"));
            },
        });
    },
});
