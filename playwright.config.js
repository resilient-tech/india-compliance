import { defineConfig, devices } from "@playwright/test";

const SITE = process.env.SITE || "localhost";
const SITE_PORT = process.env.SITE_PORT || "8000";
const BASE_URL = process.env.BASE_URL || `http://${SITE}:${SITE_PORT}`;

const STORAGE_STATE = "playwright/.auth/admin.json";

// Matches the viewport the Cypress suite ran at.
const VIEWPORT = { width: 1400, height: 960 };

export default defineConfig({
    testDir: "./playwright/tests",
    outputDir: "test-results",

    fullyParallel: false,
    workers: 4,

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
