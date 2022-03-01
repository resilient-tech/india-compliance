import IndiaComplianceAccountApp from "./IndiaComplianceAccountApp.vue";

class IndiaComplianceAccountPage {
    constructor(wrapper) {
        this.containerId = "india-compliance-account-app-container";

        // Why need container? Because Vue replaces the element with the component.
        // So, if we don't have a container, the component will be rendered on the #body
        // and removes the element #page-india-compliance-account,
        // which is required by frappe route in order to work it properly.
        $(wrapper).html(`<div id="${this.containerId}"></div>`);
        this.show();
    }

    show() {
        new Vue({
            el: `#${this.containerId}`,
            render: (h) => h(IndiaComplianceAccountApp),
        });
    }
}

frappe.provide("india_compliance.page");
india_compliance.page.IndiaComplianceAccountPage = IndiaComplianceAccountPage;
