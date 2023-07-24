import { createApp } from "vue";
import { routes } from "./router";
import { createRouter, createWebHistory } from "vue-router";
import store from "./store/index";
import IndiaComplianceAccountApp from "./IndiaComplianceAccountApp.vue";
import { get_api_secret } from "./services/AuthService";

class IndiaComplianceAccountPage {
    constructor(wrapper, pageName) {
        this.pageName = pageName;
        this.wrapperId = `#${wrapper.id}`;
        this.setTitle();
        this.show();
    }

    setTitle() {
        frappe.utils.set_title(__("India Compliance Account"));
    }

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
        const error = e.message || "Something went wrong, Please try again later!";

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
            invalid_token: e.response.exc_type?.includes("InvalidAuthorizationToken"),
        };
    }
};

function extract_error_message(responseBody) {
    const { exc_type, exception, _server_messages } = responseBody;
    if (!exception) {
        if (_server_messages) {
            const server_messages = JSON.parse(_server_messages);
            return server_messages
                .map(message => JSON.parse(message).message || "")
                .join("\n");
        }
        return "Something went wrong, Please try again later!";
    }
    return exception.replace(new RegExp(".*" + exc_type + ":", "gi"), "").trim();
}

class UnsuccessfulResponseError extends Error {
    constructor(response) {
        super(extract_error_message(response));
        this.response = response;
    }
}
