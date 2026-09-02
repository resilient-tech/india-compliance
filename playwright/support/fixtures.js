import { test as base, expect } from "@playwright/test";

import { createApi, gotoDesk } from "./frappe";

const GSP_URL = "https://asp.resilient.tech/**";

export const test = base.extend({
    blockGsp: [
        async ({ page }, use) => {
            await page.route(GSP_URL, (route) => route.abort("failed"));
            await use(true);
        },
        { auto: true },
    ],

    consoleLogs: [
        async ({ page }, use, testInfo) => {
            const lines = [];

            page.on("console", (message) => {
                lines.push(`[${message.type()}] ${message.text()}`);
            });

            await use(lines);

            if (lines.length && testInfo.status !== testInfo.expectedStatus)
                await testInfo.attach("console.log", {
                    body: lines.join("\n"),
                    contentType: "text/plain",
                });
        },
        { auto: true },
    ],

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

    desk: async ({ page, blockGsp }, use) => {
        void blockGsp; // ordering: the route must exist before the first navigation

        await gotoDesk(page);
        await use(page);
    },

    api: async ({ desk }, use) => {
        await use(createApi(desk));
    },
});

export { expect };
