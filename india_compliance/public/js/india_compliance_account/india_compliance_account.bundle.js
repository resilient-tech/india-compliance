import Vue from "vue/dist/vue.js";
import VueRouter from "vue-router/dist/vue-router.js";

import router from "./router.js";
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
        Vue.use(VueRouter);

        new Vue({
            el: `#${this.containerId}`,
            router,
            render: (h) => h(IndiaComplianceAccountApp),
        });
    }
}

frappe.provide("india_compliance.page");
india_compliance.page.IndiaComplianceAccountPage = IndiaComplianceAccountPage;
