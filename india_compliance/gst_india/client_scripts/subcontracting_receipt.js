DOCTYPE = "Subcontracting Receipt";
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

        ["supplier_address", "shipping_address"].forEach(field => {
            frm.set_query(field, function () {
                return { filters: { country: "India", disabled: 0 } };
            });
        });
    },
    onload(frm) {
        frm.taxes_controller = new india_compliance.taxes_controller(frm, {
            total_taxable_value: "total",
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

    async select_original_doc_ref(frm) {
        const data = [];
        frappe.db
            .get_list("Stock Entry", {
                filters: [
                    [
                        "Stock Entry Detail",
                        "item_code",
                        "in",
                        Array.from(frm.doc.supplied_items, row => row.rm_item_code),
                    ],
                    ["purpose", "=", "Send to Subcontractor"],
                ],
                group_by: "name",
            })
            .then(res => {
                res.forEach(row => {
                    data.push({ Doctype: "Stock Entry", Name: row.name });
                });
            });
        frappe.db
            .get_list(DOCTYPE, {
                filters: {
                    is_return: ["is", "set"],
                    supplier: ["=", frm.doc.supplier],
                },
                fields: ["name"],
            })
            .then(res => {
                res.forEach(row => {
                    data.push({ Doctype: DOCTYPE, Name: row.name });
                });
            });
        india_compliance.render_data_table(this, frm, "doc_references", data);
    },

    taxes_and_charges(frm) {
        frm.taxes_controller.update_taxes(frm);
    },
});

frappe.ui.form.on(
    "Subcontracting Receipt Item",
    india_compliance.taxes_controller_events
);
