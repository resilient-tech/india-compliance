const DOCTYPE = "Purchase Invoice";
setup_e_waybill_actions(DOCTYPE);

frappe.ui.form.on(DOCTYPE, {
    setup(frm) {
        frm.set_query("transporter", {
            filters: {
                is_transporter: 1,
            },
        });

        frm.set_query("driver", doc => {
            return {
                filters: {
                    transporter: doc.transporter,
                },
            };
        });
    },

    onload: function (frm) {
        toggle_reverse_charge(frm);

        if (frm.is_new()) {
            frm.add_custom_button(
                __("Create Invoice from IRN"),
                () => show_irn_dialog(frm),
            );
        }
    },

    gst_category(frm) {
        validate_gst_hsn_code(frm);
        toggle_reverse_charge(frm);
    },

    after_save(frm) {
        if (
            frm.doc.supplier_address ||
            !(frm.doc.gst_category == "Unregistered" || frm.doc.is_return) ||
            !is_e_waybill_applicable(frm) ||
            !has_e_waybill_threshold_met(frm)
        )
            return;

        frappe.show_alert(
            {
                message: __("Supplier Address is required to create e-Waybill"),
                indicator: "yellow",
            },
            10
        );
    },

    refresh(frm) {
        india_compliance.set_reconciliation_status(frm, "bill_no");
        if (gst_settings.enable_e_waybill && gst_settings.enable_e_waybill_from_pi)
            show_sandbox_mode_indicator();

        if (
            frm.doc.docstatus !== 1 ||
            frm.doc.gst_category !== "Overseas" ||
            frm.doc.__onload?.bill_of_entry_exists
        )
            return;

        frm.add_custom_button(
            __("Bill of Entry"),
            () => {
                frappe.model.open_mapped_doc({
                    method: "india_compliance.gst_india.doctype.bill_of_entry.bill_of_entry.make_bill_of_entry",
                    frm: frm,
                });
            },
            __("Create")
        );
    },

    before_save: function (frm) {
        // hack: values set in frm.doc are not available after save
        if (frm._inward_supply) frm.doc._inward_supply = frm._inward_supply;
    },

    on_submit: function (frm) {
        if (!frm._inward_supply) return;

        // go back to previous page and match the invoice with the inward supply
        setTimeout(() => {
            frappe.route_hooks.after_load = reco_frm => {
                if (!reco_frm.purchase_reconciliation_tool) return;
                purchase_reconciliation_tool.link_documents(
                    reco_frm,
                    frm.doc.name,
                    frm._inward_supply.name,
                    "Purchase Invoice",
                    false
                );
            };
            frappe.set_route("Form", "Purchase Reconciliation Tool");
        }, 2000);
    },
});

frappe.ui.form.on("Purchase Invoice Item", {
    item_code(frm) {
        validate_gst_hsn_code(frm);
        toggle_reverse_charge(frm);
    },

    items_remove: toggle_reverse_charge,

    gst_hsn_code: validate_gst_hsn_code,
});


function show_irn_dialog(frm) {
    const dialog = new frappe.ui.Dialog({
        title: __("Create Purchase Invoice"),
        fields: [
            {
                label: "IRN",
                fieldname: "irn",
                fieldtype: "Data",
                reqd: 1,
            },
            {
                label: "Company GSTIN",
                fieldname: "gstin",
                fieldtype: "Autocomplete",
                get_query: function () {
                    return {
                        query: "india_compliance.gst_india.overrides.purchase_invoice.get_gstin_with_company_name",
                    };
                },
                reqd: 1,
            }
        ],
        primary_action_label: 'Create',
        primary_action(values) {
            taxpayer_api.call(
                method = "india_compliance.gst_india.overrides.purchase_invoice.create_purchase_invoice_from_irn",
                args = {
                    company_gstin: values.gstin,
                    irn: values.irn,
                },
                function (r) {
                    doc = r.message;
                    dialog.hide();
                    frappe.set_route("purchase-invoice", doc.name);
                    set_party_details(doc, frm);
                },
            );
        },
    });
    dialog.show();

    frappe.db.get_value("Company", frappe.defaults.get_default("company"), "gstin").then(r => {
        dialog.fields_dict.gstin.set_input(r.message.gstin);
    })
}

function set_party_details(doc, frm) {
    erpnext.utils.get_party_details(
        frm,
        "erpnext.accounts.party.get_party_details",
        {
            posting_date: doc.posting_date,
            bill_date: doc.bill_date,
            party: doc.supplier,
            party_type: "Supplier",
            account: doc.credit_to,
            price_list: doc.buying_price_list,
            fetch_payment_terms_template: cint(!doc.ignore_default_payment_terms_template),
        },
        function () {
            frm.set_value("apply_tds", frm.supplier_tds ? 1 : 0);
            frm.set_value("tax_withholding_category", frm.supplier_tds);
            frm.set_df_property("apply_tds", "read_only", frm.supplier_tds ? 0 : 1);
            frm.set_df_property("tax_withholding_category", "hidden", frm.supplier_tds ? 0 : 1);
        }
    );
}


function toggle_reverse_charge(frm) {
    let is_read_only = 0;
    if (frm.doc.gst_category !== "Overseas") is_read_only = 0;
    // has_goods_item
    else if (frm.doc.items.some(item => !item.gst_hsn_code.startsWith("99")))
        is_read_only = 1;

    frm.set_df_property("is_reverse_charge", "read_only", is_read_only);
}

function validate_gst_hsn_code(frm) {
    if (frm.doc.gst_category !== "Overseas") return;

    if (frm.doc.items.some(item => !item.gst_hsn_code)) {
        frappe.throw(__("GST HSN Code is mandatory for Overseas Purchase Invoice."));
    }
}
