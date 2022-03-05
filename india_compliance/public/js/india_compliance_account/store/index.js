import Vuex from "vuex";
import authStore from "./auth";

export default new Vuex.Store({
    modules: {
        auth: authStore,
    },
});
