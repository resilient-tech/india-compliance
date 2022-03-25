import { get_subscription_details } from "../../services/AccountService";

export default {
    state: {
        subscription_details: null,
    },

    mutations: {
        SET_SUBSCRIPTION_DETAILS(state, subscription_details) {
            state.subscription_details = subscription_details;
        },
    },

    actions: {
        async initAccount({ dispatch }) {
            await dispatch("fetchSubscriptionDetails");
        },

        async fetchSubscriptionDetails({ commit }) {
            const response = await get_subscription_details();
            if (response.error) return this.dispatch("setApiSecret", null);
            if (!response.success || !response.message) return;
            commit("SET_SUBSCRIPTION_DETAILS", response.message);
        },
    },

    getters: {},
};
