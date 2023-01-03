let icAccountPage;
const pageName = "india-compliance-account";

frappe.pages[pageName].on_page_load = async function (wrapper) {
    await frappe.require([
        "india_compliance_account.bundle.js",
        "india_compliance_account.bundle.css",
    ]);

    icAccountPage = new ic.pages.IndiaComplianceAccountPage(wrapper, pageName);
};

frappe.pages[pageName].refresh = function (wrapper) {
    if (!icAccountPage) return;
    icAccountPage.mountVueApp();
};
