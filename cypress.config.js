const fs = require("fs");
const { defineConfig } = require("cypress");

module.exports = defineConfig({
    env: {
        adminPassword: "admin",
    },

    defaultCommandTimeout: 20000,
    pageLoadTimeout: 30000,
    responseTimeout: 60000,

    viewportWidth: 1400,
    viewportHeight: 960,

    video: true,

    retries: {
        runMode: 1,
        openMode: 0,
    },

    e2e: {
        baseUrl: "http://ic_test.localhost:8001",

        // specPattern defaults to "cypress/e2e/**/*.cy.{js,jsx,ts,tsx}" for Cypress >= 10,
        testIsolation: false,

        setupNodeEvents(on, config) {
            require("@cypress/code-coverage/task")(on, config);

            on("before:browser:launch", (browser = {}, launchOptions) => {
                if (browser.family === "chromium" && browser.name !== "electron") {
                    launchOptions.args.push("--no-sandbox");
                    launchOptions.args.push("--disable-dev-shm-usage");
                    launchOptions.args.push("--disable-gpu");
                }
                return launchOptions;
            });

            // Keep videos only for specs that failed or were retried.
            on("after:spec", (spec, results) => {
                if (!results || !results.video) return;

                const failed = results.tests.some((test) =>
                    test.attempts.some((attempt) => attempt.state === "failed"),
                );
                if (!failed) fs.unlinkSync(results.video);
            });

            return config;
        },
    },
});
