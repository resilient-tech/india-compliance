import { createStore } from 'vuex'
import authStore from "./modules/auth";
import accountStore from "./modules/account";

export default createStore({
    modules: {
        auth: authStore,
        account: accountStore,
    },
});
