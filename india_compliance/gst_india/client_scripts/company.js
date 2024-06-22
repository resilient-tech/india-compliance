{% include "india_compliance/gst_india/client_scripts/party.js" %}

const DOCTYPE = "Company";

validate_pan(DOCTYPE);
validate_gstin(DOCTYPE);
update_gstin_in_other_documents(DOCTYPE);
show_overseas_disabled_warning(DOCTYPE);
set_gstin_options_and_status(DOCTYPE);

frappe.ui.form.off(DOCTYPE, "make_default_tax_template");
frappe.ui.form.on(DOCTYPE, {
    setup(frm) {
        erpnext.company.set_custom_query(frm, [
            "default_customs_expense_account",
            { root_type: "Expense" },
        ]);
        erpnext.company.set_custom_query(frm, [
            "default_customs_payable_account",
            { root_type: "Liability" },
        ]);
<<<<<<< HEAD
=======

        frm.set_query("autofield", "bank_details_for_printing", (_, cdt, cdn) => {
            return  {
                query: "india_compliance.gst_india.overrides.company.get_default_print_options",
                params : {for_bank : 1}
            }
        });
        frm.set_query("autofield", "registration_details_for_printing", (_, cdt, cdn) => {
            return {
                query: "india_compliance.gst_india.overrides.company.get_default_print_options",
                params : {for_bank : 0}
            }
        });
>>>>>>> dd9d551c (fix: parse param correctly in py)
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
