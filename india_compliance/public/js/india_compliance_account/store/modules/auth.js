import {
    get_api_secret,
    get_session as get_session,
    validate_session,
    set_session,
    set_api_secret,
} from "../../services/AuthService";

export default {
    state: {
        api_secret: null,
        session: null,
    },

    mutations: {
        SET_API_SECRET(state, api_secret) {
            state.api_secret = api_secret;
            state.session = null;
        },

        SET_SESSION(state, session) {
            state.session = session;
        },
    },

    actions: {
        async authenticate({ state, dispatch, commit }) {
            const api_secret = await get_api_secret();
            if (api_secret) return commit("SET_API_SECRET", api_secret);

            await dispatch("fetchSession");
            if (!state.session) return;

            const response = await validate_session(state.session.id);
            if (response.error) {
                if (response.exc_type === "InvalidSessionError") {
                    // invalid session -> delete the session
                    await dispatch("setSession", null);
                }
                return;
            }
            if (!response.message || !response.message.api_secret) return;
            await dispatch("setApiSecret", response.message.api_secret);
        },

        async setSession({ commit }, session) {
            await set_session(session);
            commit("SET_SESSION", session);
        },

        async setApiSecret({ commit }, api_secret) {
            await set_api_secret(api_secret);
            commit("SET_API_SECRET", api_secret);
        },

        async fetchSession({ commit }) {
            commit("SET_SESSION", await get_session());
        },
    },

    getters: {
        isLoggedIn(state) {
            return !!state.api_secret;
        },

        hasSession(state) {
            return !!state.session;
        },

        guessRouteName(state) {
            if (state.api_secret) return "home";
            if (state.session) return "mailSent";
            return "auth";
        }
    },
};
