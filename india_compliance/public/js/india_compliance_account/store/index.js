import Vuex from "vuex";
import authStore from "./modules/auth";

export default new Vuex.Store({
    modules: {
        auth: authStore,
    },
});
