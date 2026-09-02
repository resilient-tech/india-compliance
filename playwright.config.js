import { defineConfig, devices } from "@playwright/test";

// The site is never defaulted: a wrong guess runs the suite against a
// development site and writes test data into it. Set SITE (locally via
// playwright.env in .vscode/settings.json, in CI via the workflow env), or
// BASE_URL to override the whole URL.
const SITE = process.env.SITE;
const SITE_PORT = process.env.SITE_PORT || "8000";
const BASE_URL = process.env.BASE_URL || (SITE && `http://${SITE}:${SITE_PORT}`);

if (!BASE_URL) {
    throw new Error(
        "No site configured for the UI tests. Set SITE (e.g. SITE=ic_test.localhost) " +
            "or BASE_URL (e.g. BASE_URL=http://ic_test.localhost:8000) in the " +
            "environment. For VS Code runs, set it under `playwright.env` in " +
            ".vscode/settings.json; CI sets it from the workflow env.",
    );
}

const STORAGE_STATE = "playwright/.auth/admin.json";

// Matches the viewport the Cypress suite ran at.
const VIEWPORT = { width: 1400, height: 960 };

export default defineConfig({
    testDir: "./playwright/tests",
    outputDir: "test-results",

    fullyParallel: false,
    workers: 1,

    forbidOnly: !!process.env.CI,
    retries: process.env.CI ? 1 : 0,

    reporter: process.env.CI
        ? [["github"], ["list"], ["html", { open: "never" }]]
        : [["list"], ["html", { open: "never" }]],

    timeout: 120_000,
    expect: { timeout: 20_000 },

    use: {
        baseURL: BASE_URL,
        viewport: VIEWPORT,
        actionTimeout: 20_000,
        navigationTimeout: 30_000,
        trace: "on-first-retry",
        video: "retain-on-failure",
        screenshot: "only-on-failure",
        ...(process.env.CI
            ? {
                  launchOptions: {
                      args: ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
                  },
              }
            : {}),
    },

    projects: [
        { name: "setup", testMatch: /.*\.setup\.js/ },
        {
            name: "chromium",
            use: {
                ...devices["Desktop Chrome"],
                viewport: VIEWPORT, // after the spread: the device preset is 1280x720
                storageState: STORAGE_STATE,
            },
            dependencies: ["setup"],
            testIgnore: /.*\.setup\.js/,
        },
    ],
});
