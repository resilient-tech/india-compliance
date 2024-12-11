<<<<<<< HEAD
import Vuex from "vuex";
import authStore from "./modules/auth";
import accountStore from "./modules/account";

export default new Vuex.Store({
=======
import { createStore } from 'vuex'
import authStore from "./modules/auth";
import accountStore from "./modules/account";

export default createStore({
>>>>>>> ae4792e4 (fix: correct categorisation of is_export and fetching taxes accordingly)
    modules: {
        auth: authStore,
        account: accountStore,
    },
});
