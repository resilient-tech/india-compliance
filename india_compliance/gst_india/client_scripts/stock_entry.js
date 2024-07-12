frappe.provide("india_compliance");
DOCTYPE = "Stock Entry";

setup_e_waybill_actions(DOCTYPE);

frappe.ui.form.on(DOCTYPE, {
    setup(frm) {
        frm.set_query("taxes_and_charges", function () {
            return {
                filters: [
                    ["disabled", "=", 0],
                    ["company", "=", frm.doc.company],
                ],
            };
        });

        frm.set_query("transporter", function () {
            return {
                filters: [
                    ["disabled", "=", 0],
                    ["is_transporter", "=", 1],
                ],
            };
        });

        set_address_display_events();
        set_bill_to_address(frm);
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

    supplier_address: set_bill_to_address,

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

function set_bill_to_address(frm) {
    // TODO: For Source and Target Warehouse
    const address_field = "bill_to_address";
    let read_only, label;
    if (frm.doc.supplier_address) {
        frm.set_value(address_field, frm.doc.supplier_address);
        read_only = 1;
        label = "Bill To (same as Supplier Address)";
    } else {
        read_only = 0;
        label = "Bill To";
    }

    frm.set_df_property(address_field, "read_only", read_only);
    frm.set_df_property(address_field, "label", label);
}

frappe.ui.form.on("Stock Entry Detail", india_compliance.taxes_controller_events);
