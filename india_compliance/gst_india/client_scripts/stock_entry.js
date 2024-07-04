frappe.provide("india_compliance");

setup_e_waybill_actions("Stock Entry");

frappe.ui.form.on("Stock Entry", {
    setup(frm) {
        frm.set_query("company_address", erpnext.queries.company_address_query);
        frm.set_query("taxes_and_charges", function () {
            return {
                filters: [
                    ["company", "=", frm.doc.company],
                ],
            };
        });
    },

    onload(frm) {
        frm.taxes_controller = new india_compliance.taxes_controller(frm, {
            total_taxable_value: "total_taxable_value",
        });
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
                    message: __("Supplier Address is required to create e-Waybill"),
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
        frm.taxes_controller.update_taxes(frm);
    },
});

frappe.ui.form.on("Stock Entry Detail", india_compliance.taxes_controller_events);
