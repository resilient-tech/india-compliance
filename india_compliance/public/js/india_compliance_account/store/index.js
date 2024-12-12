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
>>>>>>> 159ed757 (test: additionally test gst details for credit note with zero value)
    modules: {
        auth: authStore,
        account: accountStore,
    },
});
