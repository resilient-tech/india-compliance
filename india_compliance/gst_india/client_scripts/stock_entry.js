frappe.provide("india_compliance");

setup_e_waybill_actions("Stock Entry");

frappe.ui.form.on("Stock Entry", {
    setup(frm) {
        frm.set_query("company_address", erpnext.queries.company_address_query);
        frm.set_query("taxes_and_charges", function () {
            return {
                filters: [
                    ["company", "=", me.frm.doc.company],
                    ["docstatus", "!=", 2],
                ],
            };
        });
        fetch_gst_details(frm.doc.doctype);
    },

    onload(frm) {
        frm.taxes_controller = new india_compliance.taxes_controller(frm);
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
                    message: __("E-Way Bill is not generatable for this transaction"),
                    indicator: "yellow",
                },
                10
            );
    },

    company_address(frm) {
        if (frm.doc.company_address)
            erpnext.utils.get_address_display(
                frm,
                "company_address",
                "company_address_display",
                false
            );
    },

    company(frm) {
        frappe.call({
            method: "frappe.contacts.doctype.address.address.get_default_address",
            args: {
                doctype: "Company",
                name: frm.doc.company,
            },
            callback(r) {
                frm.set_value("company_address", r.message);
            },
        });
    },

    taxes_and_charges(frm) {
        if (frm.doc.taxes_and_charges) {
            return frm.call({
                method: "erpnext.controllers.accounts_controller.get_taxes_and_charges",
                args: {
                    master_doctype: frappe.meta.get_docfield(
                        frm.doc.doctype,
                        "taxes_and_charges",
                        frm.doc.name
                    ).options,
                    master_name: frm.doc.taxes_and_charges,
                },
                callback: function (r) {
                    if (!r.exc) {
                        frm.set_value("taxes", r.message);
                    }
                },
            });
        }
    },
});

frappe.ui.form.on("Stock Entry Detail", {
    async item_tax_template(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (!row.item_tax_template) frm.taxes_controller.update_item_wise_tax_rates();
        else await frm.taxes_controller.set_item_wise_tax_rates(cdn);
        frm.taxes_controller.update_tax_amount();
    },
});

frappe.ui.form.on("Stock Entry Taxes", {
    rate(frm, cdt, cdn) {
        frm.taxes_controller.update_tax_rate(cdt, cdn);
    },

    tax_amount(frm, cdt, cdn) {
        frm.taxes_controller.update_tax_amount(cdt, cdn);
    },

    async account_head(frm, cdt, cdn) {
        await frm.taxes_controller.set_item_wise_tax_rates(null, cdn);
        frm.taxes_controller.update_tax_amount(cdt, cdn);
    },

    async charge_type(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (!row.charge_type || row.charge_type === "Actual") {
            row.rate = 0;
            row.item_wise_tax_rates = "{}";
            frm.refresh_field("taxes");
        } else {
            await frm.taxes_controller.set_item_wise_tax_rates(null, cdn);
            frm.taxes_controller.update_tax_amount(cdt, cdn);
        }
    },
});

function fetch_gst_details(doctype) {
    const event_fields = [
        "company_gstin",
        "place_of_supply",
        "supplier_address",
        "supplier",
    ];

    const events = Object.fromEntries(
        event_fields.map(field => [
            field,
            frm =>
                update_gst_details(
                    frm,
                    "india_compliance.gst_india.overrides.stock_entry.update_party_details"
                ),
        ])
    );

    frappe.ui.form.on(doctype, events);
}

async function update_gst_details(frm, method) {
    if (!frm.doc.supplier || frm.__updating_gst_details) return;

    // wait for GSTINs to get fetched
    await frappe.after_ajax();

    const args = {
        doctype: frm.doc.doctype,
        party_details: {
            customer: frm.doc.supplier,
            customer_address: frm.doc.supplier_address,
            billing_address_gstin: frm.doc.supplier_gstin,
            gst_category: frm.doc.gst_category,
            company_gstin: frm.doc.company_gstin,
        },
        company: frm.doc.company,
    };

    india_compliance.fetch_and_update_gst_details(frm, args, method);
}
