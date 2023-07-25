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
    },
});

async function gst_invoice_warning(frm) {
    if (is_gst_invoice(frm) && !(await contains_gst_account(frm))) {
        frm.layout.show_message();
        frm.dashboard.add_comment(
            __(
                "GST is applicable for this invoice but no account from GST Settings is charged."
            ),
            "red",
            true
        );
    }
}

function is_gst_invoice(frm) {
    return (
        (frm.doc.docstatus == 1 &&
            frm.doc.is_opening != "Yes" &&
            frm.doc.company_gstin &&
            frm.doc.company_gstin != frm.doc.billing_address_gstin &&
            !frm.doc.items.some(row => row.is_non_gst) &&
            !frm.doc.items.every(row => row.is_nil_exempt)) ||
        frm.doc.is_export_with_gst
    );
}

async function contains_gst_account(frm) {
    frm.gst_accounts = await india_compliance.get_account_options(frm.doc.company);
    frm.accounts = frm.doc.taxes.map(taxes => taxes.account_head);

    return frm.accounts.some(row => frm.gst_accounts.includes(row));
}
