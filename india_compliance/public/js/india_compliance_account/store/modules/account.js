import {
    get_details,
    update_billing_details,
    create_order,
} from "../../services/AccountService";

export default {
    state: {
        subscriptionDetails: null,
        calculatorDetails: null,
        billingDetails: null,
        orderToken: null,
    },

    mutations: {
        SET_SUBSCRIPTION_DETAILS(state, subscriptionDetails) {
            state.subscriptionDetails = subscriptionDetails;
        },

        SET_CALCULATOR_DETAILS(state, calculatorDetails) {
            state.calculatorDetails = calculatorDetails;
        },

        SET_BILLING_DETAILS(state, billingDetails) {
            state.billingDetails = billingDetails;
        },

        SET_ORDER_TOKEN(state, orderToken) {
            state.orderToken = orderToken;
        },
    },

    actions: {
        async fetchDetails({ commit }, type) {
            const response = await get_details(type);
            if (response.invalid_token)
                return this.dispatch("setApiSecret", null);

            if (!response.success || !response.message)
                frappe.throw();
            commit(`SET_${type.toUpperCase()}_DETAILS`, response.message);
        },

        async updateBillingDetails({ commit }, billingDetails) {
            const response = await update_billing_details(billingDetails);
            if (response.invalid_token)
                return this.dispatch("setApiSecret", null);

            if (!response.success || !response.message)
                frappe.throw();
            commit("SET_BILLING_DETAILS", response.message);
            return response.message
        },

        async createOrder({ commit }, { credits, amount }) {
            const response = await create_order(credits, amount);
            if (response.invalid_token)
                return this.dispatch("setApiSecret", null);

            if (
                !response.success ||
                !response.message ||
                !response.message.order_token
            )
                frappe.throw();
            commit("SET_ORDER_TOKEN", response.message.order_token);
        },
    },

    getters: {},
};
