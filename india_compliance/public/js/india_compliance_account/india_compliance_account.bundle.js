<<<<<<< HEAD
import Vue from "vue";
import VueRouter from "vue-router";
import Vuex from "vuex";

import router from "./router";
=======
import { createApp } from "vue";
import { routes } from "./router";
import { createRouter, createWebHistory } from "vue-router";
>>>>>>> ae4792e4 (fix: correct categorisation of is_export and fetching taxes accordingly)
import store from "./store/index";
import IndiaComplianceAccountApp from "./IndiaComplianceAccountApp.vue";
import { get_api_secret } from "./services/AuthService";

class IndiaComplianceAccountPage {
<<<<<<< HEAD
    constructor(wrapper) {
        this.pageName = "india-compliance-account";
        this.containerId = "india-compliance-account-app-container";

        // Why need container? Because Vue replaces the element with the component.
        // So, if we don't have a container, the component will be rendered on the #body
        // and removes the element #page-india-compliance-account,
        // which is required by frappe route in order to work it properly.
        $(wrapper).html(`<div id="${this.containerId}"></div>`);
=======
    constructor(wrapper, pageName) {
        this.pageName = pageName;
        this.wrapperId = `#${wrapper.id}`;
>>>>>>> ae4792e4 (fix: correct categorisation of is_export and fetching taxes accordingly)
        this.setTitle();
        this.show();
    }

    setTitle() {
        frappe.utils.set_title(__("India Compliance Account"));
    }

<<<<<<< HEAD
    show() {
        Vue.use(VueRouter);
        Vue.use(Vuex);

        new Vue({
            el: `#${this.containerId}`,
            router,
            store,
            render: (h) => h(IndiaComplianceAccountApp),
        });

        $(frappe.pages[this.pageName]).on("show", () => {
            this.setTitle();
            router.replace({name: store.getters.isLoggedIn ? "home": "auth"});
=======
    createRouter() {
        const history = createWebHistory("/app/india-compliance-account");

        history.listen(to => {
            if (frappe.get_route_str().startsWith(this.pageName)) return;

            frappe.route_flags.replace_route = true;
            frappe.router.push_state(to);
            this.router.listening = false;
        });

        return createRouter({
            history: history,
            routes: routes,
        });
    }

    mountVueApp() {
        this.router = this.createRouter();
        this.app = createApp(IndiaComplianceAccountApp).use(this.router).use(store);
        SetVueGlobals(this.app);
        this.router.isReady().then(() => this.app.mount(this.wrapperId));
    }

    show() {
        this.mountVueApp();

        $(frappe.pages[this.pageName]).on("show", () => {
            this.router.listening = true;
            this.setTitle();
            this.router.replace(frappe.router.current_route.slice(1).join("/") || "/");
>>>>>>> ae4792e4 (fix: correct categorisation of is_export and fetching taxes accordingly)
        });
    }
}

frappe.provide("india_compliance.pages");
india_compliance.pages.IndiaComplianceAccountPage = IndiaComplianceAccountPage;

frappe.provide("india_compliance.gst_api");
india_compliance.gst_api.call = async function (endpoint, options) {
    try {
        const base_url = "https://asp.resilient.tech/v1/";
        const url = base_url + endpoint;

        const headers = { "Content-Type": "application/json" };
        if (options.headers) Object.assign(headers, options.headers);

        if (options.with_api_secret || options.api_secret) {
            const api_secret = options.api_secret || (await get_api_secret());
            headers["x-api-key"] = api_secret;
        }

        const args = {
            method: options.method || "POST",
            headers,
            mode: "cors",
        };

        if (options.body) args.body = JSON.stringify(options.body);

        const response = await fetch(url, args);
        const data = await response.json();
        if (response.ok) return { success: true, ...data };

        throw new UnsuccessfulResponseError(data);
    } catch (e) {
<<<<<<< HEAD
        const error =
            e.message || "Something went wrong, Please try again later!";
=======
        const error = e.message || "Something went wrong, Please try again later!";
>>>>>>> ae4792e4 (fix: correct categorisation of is_export and fetching taxes accordingly)

        if (!options.fail_silently) {
            frappe.msgprint({
                message: error,
                title: "Error",
                indicator: "red",
            });
        }

        return {
            ...e.response,
            success: false,
            error,
<<<<<<< HEAD
            invalid_token: e.response.exc_type?.includes(
                "InvalidAuthorizationToken"
            ),
=======
            invalid_token: e.response.exc_type?.includes("InvalidAuthorizationToken"),
>>>>>>> ae4792e4 (fix: correct categorisation of is_export and fetching taxes accordingly)
        };
    }
};

function extract_error_message(responseBody) {
    const { exc_type, exception, _server_messages } = responseBody;
    if (!exception) {
        if (_server_messages) {
            const server_messages = JSON.parse(_server_messages);
            return server_messages
<<<<<<< HEAD
                .map((message) => JSON.parse(message).message || "")
=======
                .map(message => JSON.parse(message).message || "")
>>>>>>> ae4792e4 (fix: correct categorisation of is_export and fetching taxes accordingly)
                .join("\n");
        }
        return "Something went wrong, Please try again later!";
    }
<<<<<<< HEAD
    return exception
        .replace(new RegExp(".*" + exc_type + ":", "gi"), "")
        .trim();
=======
    return exception.replace(new RegExp(".*" + exc_type + ":", "gi"), "").trim();
>>>>>>> ae4792e4 (fix: correct categorisation of is_export and fetching taxes accordingly)
}

class UnsuccessfulResponseError extends Error {
    constructor(response) {
        super(extract_error_message(response));
        this.response = response;
    }
}
