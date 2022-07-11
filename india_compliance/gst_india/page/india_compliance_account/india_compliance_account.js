frappe.pages["india-compliance-account"].on_page_load = function (wrapper) {
    if (frappe.boot.ic_api_enabled) {
        frappe.set_route("/");
    };
    frappe.require("india_compliance_account.bundle.js").then(() => {
        new ic.page.IndiaComplianceAccountPage(wrapper);
    });
};
