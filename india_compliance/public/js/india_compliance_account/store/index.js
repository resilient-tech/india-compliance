import Vuex from "vuex";

export default new Vuex.Store({
    state: {
        api_secret: null,
    },

    mutations: {
        SET_API_SECRET(state, api_secret) {
            state.api_secret = api_secret;
        },
    },

    actions: {
        async authenticate({ commit }) {
            try {
                const api_secret = await frappe
                    .call("india_compliance.gst_india.get_gst_api_secret")
                    .then(({ message }) => message);

                commit("SET_API_SECRET", api_secret);
            } catch (e) {
                commit("SET_API_SECRET", null);
            }
        },
    },

    getters: {
        isLoggedIn(state) {
            return !!state.api_secret;
        },
    },
});
