frappe.pages["india-compliance-account"].on_page_load = function (wrapper) {
    frappe.ui.make_app_page({
        parent: wrapper,
        title: "",
        single_column: true,
    });
    frappe.require("india_compliance_account.bundle.js").then(() => {
        new india_compliance.page.IndiaComplianceAccountPage({
            wrapper: wrapper,
        });
    });
};
