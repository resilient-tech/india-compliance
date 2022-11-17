let icAccountPage;

frappe.pages["india-compliance-account"].on_page_load = async function (wrapper) {
    await frappe.require([
        "india_compliance_account.bundle.js",
        "india_compliance_account.bundle.css",
    ]);

    icAccountPage = new ic.pages.IndiaComplianceAccountPage(wrapper);
};

frappe.pages["india-compliance-account"].refresh = function (wrapper) {
    if (!icAccountPage) return;
    icAccountPage.mountVueApp();
};
