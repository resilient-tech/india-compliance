frappe.listview_settings["MSME Registration"] = {
    onload(list_view) {
        if (!frappe.model.can_write("MSME Registration")) return;

        list_view.page.add_actions_menu_item(__("Copy MSME to Next Year"), () => {
            const registrations = list_view.get_checked_items(true);
            if (!registrations.length) return;

            copy_msme_to_next_year(registrations, () => list_view.refresh());
        });
    },
};

function copy_msme_to_next_year(registrations, on_copy) {
    frappe.prompt(
        {
            fieldname: "financial_year",
            label: __("Financial Year to copy the latest category to"),
            fieldtype: "Autocomplete",
            options: india_compliance.get_indian_fiscal_year_options(9, 1),
            default: india_compliance.get_indian_fiscal_year(),
            reqd: 1,
        },
        async ({ financial_year }) => {
            await frappe.xcall(
                "india_compliance.income_tax_india.doctype.msme_registration.msme_registration.copy_to_financial_year",
                { registrations, financial_year },
            );
            on_copy?.();
        },
        __("Copy MSME to Next Year"),
        __("Copy"),
    );
}
