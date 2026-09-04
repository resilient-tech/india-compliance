// Runs once per run as the `setup` project, before every other spec.
//
// Absorbs what cypress/support/session.js did in a per-spec before(): logs in,
// clears the India Compliance onboarding notifications, and leaves a storageState
// file the `chromium` project reuses, so no spec logs in again.

import fs from "node:fs";
import path from "node:path";

import { expect, test as setup } from "@playwright/test";

import { deskReady } from "../support/frappe";

const STORAGE_STATE = "playwright/.auth/admin.json";
const USER = process.env.FRAPPE_USER || "Administrator";
const PASSWORD = process.env.ADMIN_PASSWORD || "admin";

setup("authenticate and prepare the desk", async ({ page, baseURL }) => {
    // A named failure here beats a spec file's worth of ECONNREFUSED traces.
    const ping = await page.request.get("/api/method/ping").catch(() => null);
    expect(
        ping?.ok(),
        `No Frappe server at ${baseURL}. Start one with:\n\n` +
            "    cd <bench> && DEV_SERVER=true bench serve --port 8000\n\n" +
            "It must be a single-process dev server: server-side mocks in " +
            "ui_test_helpers.py keep their state in the serving process.",
    ).toBeTruthy();

    const login = await page.request.post("/api/method/login", {
        form: { usr: USER, pwd: PASSWORD },
    });
    expect(login.ok(), `login as ${USER} failed: ${await login.text()}`).toBeTruthy();

    await page.goto("/app");
    await deskReady(page);

    const csrfToken = await page.evaluate(() => window.frappe.csrf_token);
    expect(csrfToken, "no window.frappe.csrf_token — API writes would 417").toBeTruthy();

    const call = (method, data = {}) =>
        page.request.post(`/api/method/${method}`, {
            data,
            headers: { "Content-Type": "application/json", "X-Frappe-CSRF-Token": csrfToken },
        });

    // These are server-side defaults, so clearing them once per run is enough.
    const suppressed = await call("india_compliance.tests.ui_test_helpers.suppress_notifications");
    expect(
        suppressed.ok(),
        "suppress_notifications was rejected. whitelist_for_tests needs one of: " +
            "`allow_tests` on the site plus DEV_SERVER=true, or CI set in the " +
            `server's environment. Response: ${await suppressed.text()}`,
    ).toBeTruthy();
    const headroom = await call("frappe.client.set_value", {
        doctype: "User",
        name: USER,
        fieldname: "simultaneous_sessions",
        value: 10,
    });
    expect(headroom.ok(), await headroom.text()).toBeTruthy();

    fs.mkdirSync(path.dirname(STORAGE_STATE), { recursive: true });
    await page.context().storageState({ path: STORAGE_STATE });
});
