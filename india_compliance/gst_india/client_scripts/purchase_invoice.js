const DOCTYPE = "Purchase Invoice";
const IMPORT_GST_CATEGORIES = ["Overseas", "SEZ"];

setup_e_waybill_actions(DOCTYPE);

frappe.ui.form.on(DOCTYPE, {
    setup(frm) {
        frm.set_query("transporter", {
            filters: {
                is_transporter: 1,
            },
        });

        frm.set_query("driver", (doc) => {
            return {
                filters: {
                    transporter: doc.transporter,
                },
            };
        });

        india_compliance.setup_itc_claim_period_query(frm);
    },

    onload(frm) {
        toggle_reverse_charge(frm);
    },

    gst_category(frm) {
        validate_gst_hsn_code(frm);
        toggle_reverse_charge(frm);
    },

    async after_save(frm) {
        if (
            frm.doc.supplier_address ||
            !(frm.doc.gst_category == "Unregistered" || frm.doc.is_return) ||
            !is_e_waybill_applicable(frm) ||
            !(await has_e_waybill_threshold_met(frm))
        )
            return;

        frappe.show_alert(
            {
                message: __("Supplier Address is required to create e-Waybill"),
                indicator: "yellow",
            },
            10,
        );
    },

    refresh(frm) {
        india_compliance.set_reconciliation_status(frm, "bill_no");
        india_compliance.set_itc_claim_period_status(frm);
        if (gst_settings.enable_e_waybill && gst_settings.enable_e_waybill_from_pi)
            show_sandbox_mode_indicator();

        if (frm.doc.docstatus === 1 && frm.doc.is_boe_applicable && frm.doc.__onload?.has_pending_boe_qty) {
            frm.add_custom_button(
                __("Bill of Entry"),
                () => {
                    frappe.model.open_mapped_doc({
                        method: "india_compliance.gst_india.doctype.bill_of_entry.bill_of_entry.make_bill_of_entry",
                        frm: frm,
                    });
                },
                __("Create"),
            );
        }

        if (frm.doc.docstatus === 1 && frm.doc.is_isd_applicable) {
            frm.add_custom_button(
                __("ISD Invoice"),
                () => show_isd_invoice_distribution_dialog(frm),
                __("Create"),
            );
        }
    },

    before_save(frm) {
        // hack: values set in frm.doc are not available after save
        if (frm._inward_supply) frm.doc._inward_supply = frm._inward_supply;
    },

    on_submit: function (frm) {
        if (!frm._inward_supply) return;
        // go back to previous page and match the invoice with the inward supply
        setTimeout(() => {
            frappe.route_hooks.after_load = (source_frm) => {
                if (!source_frm.reconciliation_tabs) return;
                reconciliation.link_documents(
                    source_frm,
                    frm.doc.name,
                    frm._inward_supply.name,
                    "Purchase Invoice",
                    false,
                );
            };
            frappe.set_route("Form", frm._inward_supply.source_doc);
        }, 2000);
    },
});

frappe.ui.form.on("Purchase Invoice Item", {
    item_code(frm) {
        validate_gst_hsn_code(frm);
        toggle_reverse_charge(frm);
    },

    items_remove(frm) {
        toggle_reverse_charge(frm);
    },

    gst_hsn_code(frm) {
        validate_gst_hsn_code(frm);
    },
});

function toggle_reverse_charge(frm) {
    let is_read_only = 0;
    if (!is_import_gst_category(frm.doc.gst_category)) is_read_only = 0;
    // has_goods_item
    else if (has_goods_items(frm)) is_read_only = 1;

    frm.set_df_property("is_reverse_charge", "read_only", is_read_only);
}

function validate_gst_hsn_code(frm) {
    if (
        !is_import_gst_category(frm.doc.gst_category) ||
        !india_compliance.is_indian_registered_company(frm.doc.company)
    )
        return;

    if (frm.doc.items.some((item) => item.item_name && !item.gst_hsn_code)) {
        frappe.throw(__("GST HSN Code is mandatory for {0} Purchase Invoice.", [frm.doc.gst_category]));
    }
}

function has_goods_items(frm) {
    return (
        frm.doc.items.length > 0 &&
        frm.doc.items.some((item) => item.gst_hsn_code && !item.gst_hsn_code.startsWith("99"))
    );
}

function is_import_gst_category(gst_category) {
    return IMPORT_GST_CATEGORIES.includes(gst_category);
}

function show_isd_invoice_distribution_dialog(frm) {
    let fetch_addresses = () => {};
    // last column will be to narrow, frappe issue #38228
    const dialog = new frappe.ui.Dialog({
        title: __("Select Addresses for ISD Distribution"),
        size: "extra-large",
        fields: [
            {
                fieldtype: "Section Break",
                fieldname: "general_section",
            },
            {
                fieldtype: "Check",
                fieldname: "is_against_party",
                label: __("Against Party"),
                default: 0,
                change() {
                    let grid = dialog.fields_dict.distribution_heads.grid;
                    grid.update_docfield_property("party_type", "hidden", !this.get_value());
                    grid.update_docfield_property("party", "hidden", !this.get_value());
                    grid.reset_grid();
                    grid.refresh();
                },
            },
            {
                fieldtype: "Section Break",
                fieldname: "address_section",
            },
            {
                label: __("Distribution Heads"),
                fieldtype: "Table",
                fieldname: "distribution_heads",
                in_place_edit: true,
                fields: [
                    {
                        fieldtype: "Select",
                        options: ["Company", "Customer", "Supplier"],
                        fieldname: "party_type",
                        label: __("Party Type"),
                        default: "Company",
                        in_list_view: 1,
                        columns: 1,
                        hidden: 1,
                    },
                    {
                        fieldtype: "Autocomplete",
                        fieldname: "party",
                        label: __("Party"),
                        default: frm.doc.company,
                        in_list_view: 1,
                        columns: 2,
                        hidden: 1,
                        get_query: function (doc) {
                            console.log("Getting party query called", doc);
                            let party_type = doc.party_type;
                            let search_text = doc.party || "";

                            return {
                                query: "india_compliance.gst_india.utils.get_party_docs_from_party_party",
                                params: {
                                    filters: {
                                        doctype: party_type,
                                        search_text: search_text,
                                    },
                                },
                            };
                        },
                    },
                    {
                        fieldtype: "Link",
                        options: "Address",
                        fieldname: "address",
                        label: __("Address"),
                        in_list_view: 1,
                        columns: 2,
                        get_query: function (doc) {
                            return {
                                query: "frappe.contacts.doctype.address.address.address_query",
                                filters: {
                                    link_doctype: doc.party_type,
                                    link_name: doc.party,
                                },
                            };
                        },
                        change: async function () {
                            const address = this.doc.address;
                            const party_type = this.doc.party_type;
                            const party = this.doc.party;
                            const grid = dialog.fields_dict.distribution_heads.grid;
                            const row = this.doc;
                            
                            if (!address) return;
                            
                            frappe.call({
                                method: "india_compliance.gst_india.doctype.isd_invoice.isd_invoice.get_distribution_heads",
                                args: {
                                    party_type: party_type,
                                    party: party,
                                    posting_date: frm.doc.posting_date,
                                    address: address,
                                },
                                callback: (r) => {
                                    if (r.message && r.message.length > 0) {
                                        row.gstin = r.message[0].gstin;
                                        row.gst_category = r.message[0].gst_category;
                                        row.gst_state = r.message[0].gst_state;
                                        row.turnover_amount = r.message[0].turnover_amount;
                                        grid.refresh();
                                    }
                                },
                            });
                        },
                    },
                    {
                        fieldtype: "Data",
                        fieldname: "gstin",
                        label: __("GSTIN"),
                        read_only: 1,
                        in_list_view: 1,
                        columns: 1,
                    },
                    {
                        fieldtype: "Data",
                        fieldname: "gst_category",
                        label: __("GST Category"),
                        read_only: 1,
                        in_list_view: 0,
                    },
                    {
                        fieldtype: "Data",
                        fieldname: "gst_state",
                        label: __("GST State"),
                        read_only: 1,
                        in_list_view: 1,
                        columns: 1,
                    },
                    {
                        fieldtype: "Currency",
                        fieldname: "turnover_amount",
                        label: __("Turnover Amount"),
                        in_list_view: 1,
                        default: 0,
                        columns: 2,
                        change: function () {
                            let grid = this.grid || dialog.fields_dict.distribution_heads.grid;
                            let total_turnover = grid.data.reduce(
                                (sum, row) => sum + (parseFloat(row.turnover_amount) || 0),
                                0,
                            );
                            grid.data.forEach((row) => {
                                row.distribution_ratio = total_turnover
                                    ? ((parseFloat(row.turnover_amount) || 0) / total_turnover) * 100
                                    : 0;
                            });
                            grid.refresh();
                        },
                    },
                    {
                        fieldtype: "Float",
                        fieldname: "distribution_ratio",
                        label: __("Distribution Ratio (%)"),
                        in_list_view: 1,
                        read_only: 1,
                        default: 0,
                        columns: 1,
                    },
                ],
            },
        ],
        primary_action_label: __("Create ISD Invoices"),
        primary_action(values) {
            const dialog_values = dialog.get_values();
            const distribution_heads = dialog_values.distribution_heads || [];
            const rows_with_turnover = distribution_heads.filter((row) => row.turnover_amount);

            if (!rows_with_turnover.length) {
                frappe.msgprint(__("Please enter Turnover Amount for at least one row."), __("No Turnover"));
                return;
            }

            dialog.hide();

            const payload = rows_with_turnover.map((row) => {
                const amount = parseFloat(row.turnover_amount) || 0;
                return {
                    fiscal_year: erpnext.utils.get_fiscal_year(frm.doc.posting_date),
                    gstin: row.gstin || "",
                    gst_state: row.gst_state || "",
                    gst_category: row.gst_category || "",
                    amount,
                    distribution_ratio: row.distribution_ratio,
                    party_address: row.address,
                    party_type: dialog_values.is_against_party ? row.party_type : null,
                    party: dialog_values.is_against_party ? row.party : null,
                };
            });

            frappe.call({
                method: "india_compliance.gst_india.doctype.isd_invoice.isd_invoice.bulk_create_isd_invoices",
                args: {
                    rows: payload,
                    source_name: frm.doc.name,
                },
                callback(r) {
                    const { message } = r;
                    const success = message[0]
                    const invalid = message[1]
                    if(invalid) {
                        frappe.msgprint({
                            title: "Some ISD Invoices failed validations.",
                            message: invalid,
                            as_list: true
                        });
                    }
                    else {
                        frappe.msgprint({
                            title: "ISD Invoices Successfully created",
                            message: success,
                            as_list: true
                        });
                    }
                },
            });
        },
    });

    fetch_addresses = function () {
        const vals = dialog.get_values(true);
        frappe.call({
            method: "india_compliance.gst_india.doctype.isd_invoice.isd_invoice.get_distribution_heads",
            args: {
                party_type: "Company",
                party: frm.doc.company,
                posting_date: frm.doc.posting_date,
            },
            callback(r) {
                if (!r.message) return;
                const data = r.message.map((row) => ({
                    party_type: "Company",
                    party: frm.doc.company,
                    address: row.name,
                    gstin: row.gstin,
                    gst_category: row.gst_category,
                    gst_state: row.gst_state,
                    turnover_amount: row.turnover_amount,
                }));
                const grid = dialog.fields_dict.distribution_heads.grid;
                grid.df.data = data;
                grid.refresh();
                grid.fields_map.turnover_amount.change();
            },
        });
    };

    dialog.show()
    
    fetch_addresses();
}
