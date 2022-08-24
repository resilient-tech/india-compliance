import VueRouter from "vue-router";

import AuthPage from "./pages/AuthPage.vue";
import AccountPage from "./pages/AccountPage.vue";
import MailSentPage from "./pages/MailSentPage.vue";
import PurchaseCreditsPage from "./pages/PurchaseCreditsPage.vue";
import PaymentPage from "./pages/PaymentPage.vue";

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
        name: "purchaseCredits",
        path: "/purchase-credits",
        component: PurchaseCreditsPage,
    },
    {
        name: "paymentPage",
        path: "/payment-page",
        component: PaymentPage,
    },
    {
        name: "home",
        path: "/",
        component: AccountPage,
        alias: "/account",
    }
];

export default new VueRouter({
    mode: "history",
    base: "/app/india-compliance-account",
    routes: routes,
});
