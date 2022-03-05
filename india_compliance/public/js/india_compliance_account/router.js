import VueRouter from "vue-router";

import AuthPage from "./pages/AuthPage.vue";
import AccountPage from "./pages/AccountPage.vue";
import Startup from "./pages/Startup.vue";

const routes = [
    {
        name: "account",
        path: "/account",
        component: AccountPage,
    },
    {
        name: "auth",
        path: "/authentication",
        component: AuthPage,
    },
    {
        name: "startup",
        path: "/",
        component: Startup,
    },
];

export default new VueRouter({
    mode: "history",
    base: "/app/india-compliance-account",
    routes: routes,
});
