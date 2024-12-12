frappe.provide("india_compliance");
DOCTYPE = "Stock Entry";

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

        ["ship_from_address", "ship_to_address"].forEach(field => {
            frm.set_query(field, { filters: { country: "India", disabled: 0 } });
        });

        set_address_display_events();

        frm.set_query("link_doctype", "doc_references", {
            name: ["=", "Stock Entry"],
        });

        frm.set_query("link_name", "doc_references", function (doc) {
            return {
                query: "india_compliance.gst_india.overrides.subcontracting_transaction.get_stock_entry_references",
                filters: {
                    supplier: doc.supplier,
                    supplied_items: get_items(doc),
                    subcontracting_orders: [doc.subcontracting_order],
                },
            };
        });

        // No event trigger are called when form is new
        if (frm.is_new()) {
            frm.trigger("bill_to_address");
        }
    },

    onload(frm) {
        frm.taxes_controller = new india_compliance.taxes_controller(frm, {
            total_taxable_value: "total_taxable_value",
        });

        on_change_set_address(
            frm,
            "supplier_address",
            ...get_field_and_label(frm, "party_field")
        );
    },

    refresh(frm) {
        frm.get_field("bill_to_address_display")
            .$wrapper.find(".ql-editor")
            .css("white-space", "normal");
        frm.get_field("bill_from_address_display")
            .$wrapper.find(".ql-editor")
            .css("white-space", "normal");

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
        on_change_set_address(
            frm,
            "supplier_address",
            ...get_field_and_label(frm, "party_field")
        );
    },

    source_warehouse_address(frm) {
        on_change_set_address(
            frm,
            "source_warehouse_address",
            "ship_from_address",
            __("Ship From (same as Source Warehouse Address)"),
            __("Ship From")
        );
    },

    target_warehouse_address(frm) {
        on_change_set_address(
            frm,
            "target_warehouse_address",
            "ship_to_address",
            __("Ship To (same as Target Warehouse Address)"),
            __("Ship To")
        );
    },

    company(frm) {
        if (frm.doc.company && frm.doc.purpose === "Send to Subcontractor") {
            frappe.call({
                method: "frappe.contacts.doctype.address.address.get_default_address",
                args: {
                    doctype: "Company",
                    name: frm.doc.company,
                },
                callback(r) {
                    frm.set_value(
                        get_field_and_label(frm, "company_field")[0],
                        r.message
                    );
                },
            });
        }
    },

    taxes_and_charges(frm) {
        frm.taxes_controller.update_taxes(frm);
    },

    async fetch_original_doc_ref(frm) {
        let existing_references = frm.doc.doc_references.map(row => row.link_name);

        data = await frappe.db.get_list(DOCTYPE, {
            filters: get_filters_for_relevant_stock_entries(frm.doc),
            group_by: "name",
        });

        data.forEach(doc => {
            if (existing_references.includes(doc.name)) return;
            var row = frm.add_child("doc_references");
            row.link_doctype = DOCTYPE;
            row.link_name = doc.name;
        });

        frm.refresh_field("doc_references");
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

function on_change_set_address(frm, source_field, target_field, label1, label2) {
    if (frm.doc.docstatus > 0) return;
    let read_only;
    let value = frm.doc[source_field];
    if (value) {
        frm.set_value(target_field, value);
        read_only = 1;
    } else {
        read_only = 0;
    }

    frm.set_df_property(target_field, "read_only", read_only);
    frm.set_df_property(target_field, "label", read_only ? label1 : label2);
}

frappe.ui.form.on("Stock Entry Detail", india_compliance.taxes_controller_events);

function get_filters_for_relevant_stock_entries(doc) {
    return [
        ["docstatus", "=", 1],
        ["purpose", "=", "Send to Subcontractor"],
        ["subcontracting_order", "=", doc.subcontracting_order],
        ["Stock Entry Detail", "item_code", "in", get_items(doc)],
    ];
}

function get_items(doc) {
    return Array.from(new Set(doc.items.map(row => row.item_code)));
}

function get_field_and_label(frm, field) {
    let field_label_dict = {};

    if (frm.doc.purpose === "Material Transfer" && frm.doc.is_return) {
        field_label_dict = {
            party_field: [
                "bill_from_address",
                __("Bill From (same as Supplier Address)"),
                __("Bill From"),
            ],
            company_field: ["bill_to_address", __("Bill To")],
        };
    } else {
        field_label_dict = {
            party_field: [
                "bill_to_address",
                __("Bill To (same as Supplier Address)"),
                __("Bill To"),
            ],
            company_field: ["bill_from_address", __("Bill From")],
        };
    }

    return field_label_dict[field];
}
