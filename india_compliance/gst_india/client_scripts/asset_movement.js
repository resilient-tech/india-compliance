frappe.provide("india_compliance");
const DOCTYPE = "Asset Movement";

frappe.ui.form.on(DOCTYPE, {
    setup(frm) {
        frm.set_query("taxes_and_charges", () => ({
            filters: [
                ["disabled", "=", 0],
                ["company", "=", frm.doc.company],
            ],
        }));

        frm.set_query("transporter", {
            filters: [
                ["disabled", "=", 0],
                ["is_transporter", "=", 1],
            ],
        });

        ["bill_from_address", "bill_to_address", "ship_from_address", "ship_to_address"].forEach((field) => {
            frm.set_query(field, { filters: { country: "India", disabled: 0 } });
        });

        india_compliance.set_address_display_events(DOCTYPE);
    },

    onload(frm) {
        frm.taxes_controller = new india_compliance.taxes_controller(frm);
    },

    refresh(frm) {
        ["bill_from_address_display", "bill_to_address_display"].forEach((field) => {
            frm.get_field(field)?.$wrapper.find(".ql-editor").css("white-space", "normal");
        });
    },

    company(frm) {
        if (!frm.doc.company || !india_compliance.is_e_waybill_applicable_for_asset_movement(frm.doc)) return;

        frappe.call({
            method: "frappe.contacts.doctype.address.address.get_default_address",
            args: { doctype: "Company", name: frm.doc.company },
            callback(r) {
                if (r.message) frm.set_value("bill_from_address", r.message);
            },
        });
    },

    taxes_and_charges(frm) {
        frm.taxes_controller.update_taxes(frm);
    },

    async tax_category(frm) {
        if (!frm.doc.assets?.length) return;

        await frappe.call({
            method: "india_compliance.gst_india.overrides.asset_movement.update_item_tax_template",
            args: { doc: frm.doc },
        });

        frm.refresh_field("assets");
        frm.taxes_controller.update_tax_amount();
    },
});

frappe.ui.form.on("Asset Movement Item", {
    item_tax_template: india_compliance.taxes_controller_events.item_tax_template,

    async asset(frm, cdt, cdn) {
        const row = locals[cdt][cdn];

        if (!row.asset) {
            await frappe.model.set_value(cdt, cdn, "taxable_value", 0);
            return;
        }

        const value_after_depreciation = await frappe.xcall(
            "erpnext.assets.doctype.asset.asset.get_asset_value_after_depreciation",
            { asset_name: row.asset },
        );

        await frappe.model.set_value(cdt, cdn, "taxable_value", value_after_depreciation);
    },

    taxable_value(frm, cdt, cdn) {
        frm.taxes_controller.update_item_taxable_value(cdt, cdn);
        frm.taxes_controller.update_tax_amount();
    },

    assets_remove(frm) {
        frm.taxes_controller.update_tax_amount();
    },
});
