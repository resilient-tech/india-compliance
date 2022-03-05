import authService from "../services/AuthService";

export default {
    state: {
        api_secret: null,
        is_auth_email_sent: false,
    },

    mutations: {
        SET_API_SECRET(state, api_secret) {
            state.api_secret = api_secret;
        },

        SET_IS_AUTH_EMAIL_SENT(state, value) {
            state.is_auth_email_sent = value;
        },
    },

    actions: {
        async initAuth({ dispatch }) {
            await dispatch("authenticate");
            await dispatch("fetchIsAuthEmailSent");
        },

        async authenticate({ commit, getters }) {
            commit("SET_API_SECRET", await authService.get_api_secret());
            if (getters.api_secret) dispatch("setIsAuthEmailSent", false);
        },

        setIsAuthEmailSent({ commit }, value) {
            localStorage.setItem("is_auth_email_sent", value);
            commit("SET_IS_AUTH_EMAIL_SENT", value);
        },

        fetchIsAuthEmailSent({ commit }) {
            commit(
                "SET_IS_AUTH_EMAIL_SENT",
                localStorage.getItem("is_auth_email_sent")
            );
        },
    },

    getters: {
        isLoggedIn(state) {
            return !!state.api_secret;
        },
    },
};
