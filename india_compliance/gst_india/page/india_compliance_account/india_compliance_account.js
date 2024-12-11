<<<<<<< HEAD
frappe.pages["india-compliance-account"].on_page_load = async function (wrapper) {
=======
const PAGE_NAME = "india-compliance-account";
let icAccountPage;

frappe.pages[PAGE_NAME].on_page_load = async function (wrapper) {
>>>>>>> ae4792e4 (fix: correct categorisation of is_export and fetching taxes accordingly)
    await frappe.require([
        "india_compliance_account.bundle.js",
        "india_compliance_account.bundle.css",
    ]);

<<<<<<< HEAD
    new india_compliance.pages.IndiaComplianceAccountPage(wrapper);
=======
    icAccountPage = new india_compliance.pages.IndiaComplianceAccountPage(wrapper, PAGE_NAME);
>>>>>>> ae4792e4 (fix: correct categorisation of is_export and fetching taxes accordingly)
};
