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
