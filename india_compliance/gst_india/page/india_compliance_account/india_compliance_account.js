frappe.pages["india-compliance-account"].on_page_load = async function (wrapper) {
    await frappe.require([
        "india_compliance_account.bundle.js",
        "india_compliance_account.bundle.css",
    ]);

    new india_compliance.pages.IndiaComplianceAccountPage(wrapper);
};
