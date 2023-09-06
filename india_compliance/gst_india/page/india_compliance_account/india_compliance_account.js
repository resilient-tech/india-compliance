frappe.pages["india-compliance-account"].on_page_load = async function (wrapper) {
    await frappe.require([
        "india_compliance_account.bundle.js",
        "india_compliance_account.bundle.css",
    ]);

<<<<<<< HEAD
    new india_compliance.pages.IndiaComplianceAccountPage(wrapper);
=======
    icAccountPage = new india_compliance.pages.IndiaComplianceAccountPage(wrapper, PAGE_NAME);
>>>>>>> 6bc8b301 (feat: Purchase Reconciliation Tool (#192))
};
