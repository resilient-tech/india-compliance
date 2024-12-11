<<<<<<< HEAD
import VueRouter from "vue-router";

=======
>>>>>>> ae4792e4 (fix: correct categorisation of is_export and fetching taxes accordingly)
import AuthPage from "./pages/AuthPage.vue";
import AccountPage from "./pages/AccountPage.vue";
import MailSentPage from "./pages/MailSentPage.vue";
import PurchaseCreditsPage from "./pages/PurchaseCreditsPage.vue";
import PaymentPage from "./pages/PaymentPage.vue";

<<<<<<< HEAD
const routes = [
=======
export const routes = [
>>>>>>> ae4792e4 (fix: correct categorisation of is_export and fetching taxes accordingly)
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
<<<<<<< HEAD
    }
];

export default new VueRouter({
    mode: "history",
    base: "/app/india-compliance-account",
    routes: routes,
});
=======
    },
];

export const AUTH_ROUTES = ["auth", "mailSent"];
>>>>>>> ae4792e4 (fix: correct categorisation of is_export and fetching taxes accordingly)
