const DOCTYPE = "Sales Invoice";
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

        frm.set_query("port_address", {
            filters: {
                country: "India",
            },
        });
    },

    before_submit(frm) {
        frm.doc._submitted_from_ui = 1;
    },

    refresh(frm) {
        gst_invoice_warning(frm);

        if (frm.doc.e_waybill_status === "Generated" && frm.doc.ewaybill) {
            frm.set_df_property("e_waybill_status", "read_only", 1);
        }
    },
});

async function gst_invoice_warning(frm) {
    if (is_gst_invoice(frm) && !(await contains_gst_account(frm))) {
        frm.dashboard.add_comment(
            __(
                `GST is applicable for this invoice but no tax accounts specified in <a href="/app/gst-settings">
                GST Settings</a> are charged.`
            ),
            "red",
            true
        );
    }
}

function is_gst_invoice(frm) {
    const gst_invoice_conditions =
        !frm.is_dirty() &&
        frm.doc.is_opening != "Yes" &&
        frm.doc.company_gstin &&
        frm.doc.company_gstin != frm.doc.billing_address_gstin &&
        !frm.doc.items.some(item => item.is_non_gst) &&
        !frm.doc.items.every(item => item.is_nil_exempt);

    if (frm.doc.place_of_supply === "96-Other Countries") {
        return gst_invoice_conditions && frm.doc.is_export_with_gst;
    } else {
        return gst_invoice_conditions;
    }
}

async function contains_gst_account(frm) {
    const gst_accounts = await _get_account_options(frm.doc.company);
    const accounts = frm.doc.taxes.map(taxes => taxes.account_head);

    return accounts.some(account => gst_accounts.includes(account));
}

async function _get_account_options(company) {
    if (!frappe.flags.gst_accounts) {
        frappe.flags.gst_accounts = {};
    }

    if (!frappe.flags.gst_accounts[company]) {
        frappe.flags.gst_accounts[company] = await india_compliance.get_account_options(
            company
        );
    }

    return frappe.flags.gst_accounts[company];
}
