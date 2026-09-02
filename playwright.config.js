import { defineConfig, devices } from "@playwright/test";

const BASE_URL = process.env.BASE_URL || "http://ic_test.localhost:8000";
const STORAGE_STATE = "playwright/.auth/admin.json";

// Matches the viewport the Cypress suite ran at.
const VIEWPORT = { width: 1400, height: 960 };

export default defineConfig({
    testDir: "./playwright/tests",
    outputDir: "test-results",

    // Desk specs share server state that cannot be partitioned: the GST Settings
    // single and the seeded test records. They also run against a single-process
    // `bench serve`. One worker, in file order.
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
        launchOptions: {
            args: ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        },
    },

    // There is deliberately no `webServer`: `bench serve` runs from the bench
    // root two levels up and needs MariaDB and Redis already running, so this
    // suite expects `bench start` to be up. auth.setup.js pings the server
    // instead and fails with the command to run.
    //
    // The bench must NOT set `serve_default_site`: that pins the dev server to
    // one site whatever the Host header says, and every spec would silently run
    // against the default site instead of the test site.
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
