import Vuex from "vuex";
import authStore from "./modules/auth";
import accountStore from "./modules/account";

export default new Vuex.Store({
    modules: {
        auth: authStore,
        account: accountStore,
    },
});
