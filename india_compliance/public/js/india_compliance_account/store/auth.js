import authService from "../services/AuthService";

export default {
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
            commit("SET_API_SECRET", await authService.get_api_secret());
        },
    },

    getters: {
        isLoggedIn(state) {
            return !!state.api_secret;
        },
    },
};
