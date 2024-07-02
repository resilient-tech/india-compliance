frappe.provide("india_compliance");

setup_e_waybill_actions("Stock Entry");
const FIELD_MAP = { tax_amount: "base_tax_amount_after_discount_amount" };

frappe.ui.form.on("Stock Entry", {
    setup(frm) {
        frm.set_query("company_address", erpnext.queries.company_address_query);
        frm.set_query("taxes_and_charges", function () {
            return {
                filters: [
                    ["company", "=", frm.doc.company],
                    ["docstatus", "!=", 2],
                ],
            };
        });
    },

    onload(frm) {
        frm.taxes_controller = new india_compliance.taxes_controller(frm, FIELD_MAP);
    },

    refresh(frm) {
        if (!gst_settings.enable_e_waybill || !gst_settings.enable_e_waybill_for_sc)
            return;

        show_sandbox_mode_indicator();
    },

    after_save(frm) {
        if (is_e_waybill_applicable(frm) && !is_e_waybill_generatable(frm))
            frappe.show_alert(
                {
                    message: __("E-Way Bill is not generatable for this transaction"),
                    indicator: "yellow",
                },
                10
            );
    },

    company_address(frm) {
        if (frm.doc.company_address)
            erpnext.utils.get_address_display(
                frm,
                "company_address",
                "company_address_display",
                false
            );
    },

    company(frm) {
        frappe.call({
            method: "frappe.contacts.doctype.address.address.get_default_address",
            args: {
                doctype: "Company",
                name: frm.doc.company,
            },
            callback(r) {
                frm.set_value("company_address", r.message);
            },
        });
    },

    taxes_and_charges(frm) {
        india_compliance.update_taxes(frm);
    },
});
