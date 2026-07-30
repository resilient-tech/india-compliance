frappe.ui.form.on("Asset Movement Item", {
    async asset(frm, cdt, cdn) {
        const row = locals[cdt][cdn];

        if (!row.asset) {
            frappe.model.set_value(cdt, cdn, "taxable_value", 0);
            return;
        }

        // Used capital goods are usually moved at their written down value
        const value_after_depreciation = await frappe.xcall(
            "erpnext.assets.doctype.asset.asset.get_asset_value_after_depreciation",
            { asset_name: row.asset },
        );

        frappe.model.set_value(cdt, cdn, "taxable_value", value_after_depreciation);
    },
});
