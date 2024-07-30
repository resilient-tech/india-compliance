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

        frm.set_query("link_doctype", "doc_references", function (doc, cdt, cdn) {
            return {
                filters: {
                    name: ["in", [doc.doctype, "Stock Entry"]],
                },
            };
        });

        frm.set_query("link_name", "doc_references", function (doc, cdt, cdn) {
            return {
                filters: {
                    supplier: ["=", frm.doc.supplier],
                    docstatus: 1,
                },
            };
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

    async fetch_original_doc_ref(frm) {
        await frappe.call({
            method: "india_compliance.gst_india.overrides.subcontracting_transaction.get_original_doc_ref_data",
            args: {
                supplier: frm.doc.supplier,
                supplied_items: frm.doc.supplied_items.map(row => row.rm_item_code),
            },
            callback: function (r) {
                r["message"].forEach(docs => {
                    let row = frm.add_child("doc_references");
                    row.link_doctype = docs.doctype;
                    row.link_name = docs.name;
                });
                frm.refresh_field("doc_references");
            },
        });
    },

    taxes_and_charges(frm) {
        frm.taxes_controller.update_taxes(frm);
    },
});

frappe.ui.form.on(
    "Subcontracting Receipt Item",
    india_compliance.taxes_controller_events
);
