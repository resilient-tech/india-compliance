frappe.provide("india_compliance");
DOCTYPE = "Stock Entry";

setup_e_waybill_actions(DOCTYPE);

frappe.ui.form.on(DOCTYPE, {
    setup(frm) {
        frm.set_query("taxes_and_charges", function () {
            return {
                filters: [["company", "=", frm.doc.company]],
            };
        });

        frm.set_query("transporter", function () {
            return {
                filters: [["is_transporter", "=", 1]],
            };
        });

        set_address_display_events();
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

    supplier_address(frm) {
        if (frm.doc.supplier_address) {
            frm.set_value("bill_to_address", frm.doc.supplier_address);
            frm.set_df_property("bill_to_address", "read_only", 1);
            frm.set_df_property(
                "bill_to_address",
                "description",
                "The 'Bill To' address is automatically populated based on the supplier address. To update the 'Bill To' address, please modify the supplier address accordingly."
            );
        } else {
            frm.set_df_property("bill_to_address", "read_only", 0);
            frm.set_df_property("bill_to_address", "description", "");
        }
    },

    company(frm) {
        if (frm.doc.company) {
            frappe.call({
                method: "frappe.contacts.doctype.address.address.get_default_address",
                args: {
                    doctype: "Company",
                    name: frm.doc.company,
                },
                callback(r) {
                    frm.set_value("bill_from_address", r.message);
                },
            });
        }
    },

    taxes_and_charges(frm) {
        frm.taxes_controller.update_taxes(frm);
    },
});

function set_address_display_events() {
    // TODO: OnChange or removal of address
    const event_fields = [
        "bill_from_address",
        "bill_to_address",
        "ship_from_address",
        "ship_to_address",
    ];

    const events = Object.fromEntries(
        event_fields.map(field => [
            field,
            frm => {
                if (frm.doc[field])
                    erpnext.utils.get_address_display(
                        frm,
                        field,
                        field + "_display",
                        false
                    );
            },
        ])
    );

    frappe.ui.form.on(DOCTYPE, events);
}

frappe.ui.form.on("Stock Entry Detail", india_compliance.taxes_controller_events);
