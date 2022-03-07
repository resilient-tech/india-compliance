import VueRouter from "vue-router";

import AuthPage from "./pages/AuthPage.vue";
import AccountPage from "./pages/AccountPage.vue";
import MailSentPage from "./pages/MailSentPage.vue";
import PageNotFound from "./pages/PageNotFound.vue";

const routes = [
    {
        name: "auth",
        path: "/authentication",
        component: AuthPage,
    },
    {
        name: "mailSent",
        path: "/mail-sent",
        component: MailSentPage,
    },
    {
        name: "home",
        path: "/",
        component: AccountPage,
        alias: "/account",
    },
    {
        path: "*",
        component: PageNotFound,
    },
];

export default new VueRouter({
    mode: "history",
    base: "/app/india-compliance-account",
    routes: routes,
});
