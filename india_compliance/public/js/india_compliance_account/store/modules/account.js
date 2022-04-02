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
        async initAccount({ dispatch }) {
            await dispatch("fetchDetails", "subscription");
        },

        async fetchDetails({ commit }, type) {
            const response = await get_details(type);
            if (response.error) return handleInvalidTokenError(response);
            if (!response.success || !response.message) return;
            commit(`SET_${type.toUpperCase()}_DETAILS`, response.message);
        },

        async updateBillingDetails({ commit }, billingDetails) {
            const response = await update_billing_details(billingDetails);
            if (response.error) return handleInvalidTokenError(response);
            if (!response.success || !response.message) return;
            commit("SET_BILLING_DETAILS", response.message);
        },

        async createOrder({ commit }, { credits, amount }) {
            const response = await create_order(credits, amount);
            if (response.error) return handleInvalidTokenError(response);
            if (
                !response.success ||
                !response.message ||
                !response.message.order_token
            )
                return;
            commit("SET_ORDER_TOKEN", response.message.order_token);
        },
    },

    getters: {},
};

async function handleInvalidTokenError({ exc_type }) {
    if (!exc_type?.includes("InvalidAuthorizationToken")) return;
    // invalid secret -> delete the secret
    await this.dispatch("setApiSecret", null);
}
