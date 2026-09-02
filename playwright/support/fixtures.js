// Shared fixtures. Import `test` and `expect` from here, not from
// @playwright/test, so every spec gets the desk session and the GSP guard rail.
//
// Note for future server-side mocks: any ui_test_helpers.py helper that keeps
// module-level state (an active `responses` interception, say) only patches the
// worker that served the request. Those helpers require the single-process
// `DEV_SERVER=true bench serve` that auth.setup.js checks for — not a multi-worker
// gunicorn.

import { test as base, expect } from "@playwright/test";

import { createApi, gotoDesk } from "./frappe";

const GSP_URL = "https://asp.resilient.tech/**";

export const test = base.extend({
    /**
     * Was the beforeEach cy.intercept in cypress/support/e2e.js. The production
     * GSP calls are made server-side by `requests`, so this is a guard rail
     * against the browser ever reaching the live gateway, not a mock.
     */
    blockGsp: [
        async ({ page }, use) => {
            await page.route(GSP_URL, (route) => route.abort("failed"));
            await use(true);
        },
        { auto: true },
    ],

    /**
     * frappe's Cypress support did `Cypress.on("uncaught:exception", () => false)`,
     * blanket-swallowing page errors. Playwright does not fail on them either, so
     * dropping that hook changes no verdicts — but real desk exceptions would go
     * unseen. Log them; set STRICT_PAGE_ERRORS=1 to fail on them.
     */
    pageErrors: [
        async ({ page }, use, testInfo) => {
            const errors = [];

            page.on("pageerror", (error) => {
                errors.push(error);
                console.warn(`[pageerror] ${testInfo.title}: ${error.message}`);
            });

            await use(errors);

            if (process.env.STRICT_PAGE_ERRORS && errors.length)
                throw new Error(`Uncaught page errors:\n${errors.join("\n")}`);
        },
        { auto: true },
    ],

    /** A page already on the desk, booted and settled. */
    desk: async ({ page, blockGsp }, use) => {
        void blockGsp; // ordering: the route must exist before the first navigation

        await gotoDesk(page);
        await use(page);
    },

    /** Whitelisted-method / REST client sharing the desk page's session. */
    api: async ({ desk }, use) => {
        await use(createApi(desk));
    },
});

export { expect };
