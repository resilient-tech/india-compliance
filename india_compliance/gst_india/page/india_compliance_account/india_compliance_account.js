frappe.pages["india-compliance-account"].on_page_load = function (wrapper) {
    frappe.require("india_compliance_account.bundle.js").then(() => {
        new india_compliance.page.IndiaComplianceAccountPage(wrapper);
    });
};
