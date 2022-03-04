import Vue from "vue/dist/vue.js";
import VueRouter from "vue-router/dist/vue-router.js";
import IndiaComplianceAccountApp from "./IndiaComplianceAccountApp.vue";
import AuthPage from "./pages/AuthPage.vue";
import AccountPage from "./pages/AccountPage.vue";
import Startup from "./pages/Startup.vue";

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
        const routes = [
            {
                name: "account",
                path: "/account",
                component: AccountPage,
            },
            {
                name: "auth",
                path: "/authentication",
                component: AuthPage,
            },
            {
                name: "startup",
                path: "/",
                component: Startup,
            },
        ];

        const router = new VueRouter({
            mode: "history",
            base: "/app/india-compliance-account",
            routes: routes,
        });

        new Vue({
            el: `#${this.containerId}`,
            router,
            render: (h) => h(IndiaComplianceAccountApp),
        });
    }
}

frappe.provide("india_compliance.page");
india_compliance.page.IndiaComplianceAccountPage = IndiaComplianceAccountPage;
