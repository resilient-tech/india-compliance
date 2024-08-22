DOCTYPE = "Subcontracting Receipt";
setup_e_waybill_actions(DOCTYPE);

frappe.ui.form.on(DOCTYPE, {
    setup(frm) {
        frm.set_query("taxes_and_charges", {
            filters: [
                ["disabled", "=", 0],
                ["company", "=", frm.doc.company],
            ],
        });

        frm.set_query("transporter", {
            filters: [
                ["disabled", "=", 0],
                ["is_transporter", "=", 1],
            ],
        });

        ["supplier_address", "shipping_address"].forEach(field => {
            frm.set_query(field, { filters: { country: "India", disabled: 0 } });
        });

        frm.set_query("link_doctype", "doc_references", {
            filters: {
                name: ["in", ["Subcontracting Receipt", "Stock Entry"]],
            },
        });

        frm.set_query("link_name", "doc_references", function (doc, cdt, cdn) {
            const row = locals[cdt][cdn];
            const subcontracting_orders = get_subcontracting_orders(doc);

            // same as backend query in get_relevant_references
            if (row.link_doctype == "Stock Entry") {
                const supplied_items = get_supplied_items(doc);
                return {
                    filters: [
                        ["docstatus", "=", 1],
                        ["purpose", "=", "Send to Subcontractor"],
                        ["subcontracting_order", "in", subcontracting_orders],
                        ["supplier", "=", doc.supplier],
                        ["Stock Entry Detail", "item_code", "in", supplied_items],
                    ],
                };
            } else if (row.link_doctype == "Subcontracting Receipt") {
                const received_items = get_received_items(doc);
                return {
                    filters: [
                        ["docstatus", "=", 1],
                        ["is_return", "=", 1],
                        ["supplier", "=", doc.supplier],
                        [
                            "Subcontracting Receipt Item",
                            "item_code",
                            "in",
                            received_items,
                        ],
                        [
                            "Subcontracting Receipt Item",
                            "subcontracting_order",
                            "in",
                            subcontracting_orders,
                        ],
                    ],
                };
            }
        });
    },
    onload(frm) {
        frm.taxes_controller = new india_compliance.taxes_controller(frm, {
            total_taxable_value: "total",
        });
    },

    refresh() {
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

    fetch_original_doc_ref(frm) {
        let existing_references = get_existing_references(frm);

        frappe.call({
            method: "india_compliance.gst_india.overrides.subcontracting_transaction.get_relevant_references",
            args: {
                supplier: frm.doc.supplier,
                supplied_items: get_supplied_items(frm.doc),
                received_items: get_received_items(frm.doc),
                subcontracting_orders: get_subcontracting_orders(frm.doc),
            },
            callback: function (r) {
                if (!r.message) return;

                Object.entries(r.message).forEach(([doctype, docnames]) => {
                    docnames.forEach(docname => {
                        if (existing_references[doctype]?.includes(docname)) return;

                        let row = frm.add_child("doc_references");
                        row.link_doctype = doctype;
                        row.link_name = docname;
                    });
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

function get_existing_references(frm) {
    let existing_references = {};

    frm.doc.doc_references.forEach(row => {
        if (!existing_references[row.link_doctype])
            existing_references[row.link_doctype] = [];
        existing_references[row.link_doctype].push(row.link_name);
    });

    return existing_references;
}

function get_supplied_items(doc) {
    return Array.from(new Set(doc.supplied_items.map(row => row.rm_item_code)));
}

function get_received_items(doc) {
    return Array.from(new Set(doc.items.map(row => row.item_code)));
}

function get_subcontracting_orders(doc) {
    return Array.from(new Set(doc.items.map(row => row.subcontracting_order)));
}
