// Replacements for the frappe Cypress commands this app used to inherit from
// apps/frappe/cypress/support/commands.js. Nothing here is app-specific: it is
// the Frappe Desk driven through Playwright.

import { expect } from "@playwright/test";

export function slug(doctype) {
    return doctype.toLowerCase().replace(/ /g, "-");
}

/**
 * cy.desk_ready(). Stricter than the original: `ajax_count === 0` is also true in
 * the gap before a request starts, so we additionally require that request.js has
 * not just flipped body[data-ajax-state] to "triggered".
 */
export async function deskReady(page) {
    await page.waitForFunction(
        () => {
            const f = window.frappe;
            if (!f?.app) return false;
            if (f.request.ajax_count !== 0) return false;

            return document.body.dataset.ajaxState !== "triggered";
        },
        undefined,
        { timeout: 30_000 },
    );

    await expect(page.locator(".layout-main-section:visible").first()).not.toBeEmpty();
}

/** /app, not /desk: both resolve server-side, but the router rewrites to /app. */
export async function gotoDesk(page, route = "/app") {
    await page.goto(route);
    await deskReady(page);
}

/** cy.new_form(). */
export async function newForm(page, doctype) {
    const dt = slug(doctype);
    await page.goto(`/app/${dt}/new`);

    const body = page.locator("body");
    await expect(body).toHaveAttribute("data-route", new RegExp(`^Form/${doctype}/new-${dt}-`));
    await expect(body).toHaveAttribute("data-ajax-state", "complete");

    await deskReady(page);
}

const INPUT_SELECTOR = {
    Select: (f) => `[data-fieldname="${f}"]:not(.search) select:visible`,
    "Text Editor": (f) => `[data-fieldname="${f}"] .ql-editor[contenteditable=true]:visible`,
    Code: (f) => `[data-fieldname="${f}"] .ace_text-input`,
    "Markdown Editor": (f) => `[data-fieldname="${f}"] .ace-editor-target`,
};

const DEFAULT_INPUT = (f) => `[data-fieldname="${f}"]:not(.search) input:visible`;

/**
 * cy.get_field(). `scope` is a Page or any Locator, so the same call works inside
 * an open grid row — that is what replaces cy.within().
 */
export function fieldInput(scope, fieldname, fieldtype = "Data") {
    const build = INPUT_SELECTOR[fieldtype] || DEFAULT_INPUT;

    return scope.locator(build(fieldname)).first();
}

/**
 * Link / Dynamic Link. Awesomplete wraps the input in <div class="awesomplete">
 * and puts a <ul role="listbox"> of <div role="option"> beside it, so the dropdown
 * is always `input.parent > [role=listbox]`.
 *
 * frappe debounces the search by 500ms (form/controls/link.js), so this never
 * sleeps: it types, then waits for the *result* to name the value we typed.
 * Matching the full typed string is what makes a stale debounce benign — a
 * neighbouring record cannot contain it. The final toHaveValue is the real guard:
 * it fails loudly if Enter picked the wrong option.
 */
async function fillLink(input, value) {
    const term = String(value);
    const dropdown = input.locator("xpath=..").getByRole("listbox");

    await input.click();
    await input.fill("");
    await expect(dropdown, `link dropdown for "${term}" never opened`).toBeVisible();

    await input.pressSequentially(term, { delay: 50 });

    await expect(
        dropdown.getByRole("option").first(),
        `no link result matching "${term}" — is the record seeded, and does the ` +
            "link_filter on this field exclude it?",
    ).toContainText(term);

    await input.press("Enter");
    await input.blur();

    await expect(dropdown).toBeHidden();
    await expect(input).toHaveValue(term);

    return input;
}

/** cy.fill_field(). */
export async function fillField(scope, fieldname, value, fieldtype = "Data") {
    const input = fieldInput(scope, fieldname, fieldtype);

    if (fieldtype === "Link" || fieldtype === "Dynamic Link") return fillLink(input, value);

    if (fieldtype === "Select") {
        await input.selectOption(String(value));

        return input;
    }

    await input.click();

    if (["Date", "Time", "Datetime"].includes(fieldtype)) {
        await expect(input.page().locator(".datepickers-container .datepicker.active")).toBeVisible();
    }

    await input.fill(String(value));
    await input.blur();

    return input;
}

/** cy.get_table_field(). */
export function tableField(page, tablefieldname, rowIdx, fieldname, fieldtype = "Data") {
    const row = page.locator(`.frappe-control[data-fieldname="${tablefieldname}"] [data-idx="${rowIdx}"]`);
    const cell = row.locator(`[data-fieldname="${fieldname}"]`);

    if (fieldtype === "Text Editor") return cell.locator(".ql-editor[contenteditable=true]").first();

    if (fieldtype === "Code") return cell.locator(".ace_text-input").first();

    return cell.locator(".form-control:visible, .static-area:visible").first();
}

/** cy.click_action_button(). Page dropdowns body-portal as espresso menus. */
export async function clickActionButton(page, name) {
    await page.getByRole("button", { name: "Actions" }).click();
    await page.locator('.es-menu [role="menuitem"]', { hasText: name }).first().click();
}

/**
 * cy.call() / cy.insert_doc() / cy.get_doc() / cy.get_list(), bound to a live
 * desk page.
 *
 * `page.request` shares the browser context's cookie jar, so the storageState
 * `sid` authenticates every call with no second login. The CSRF token is read out
 * of the page on each call rather than cached: it belongs to the session, and a
 * spec that logs out and back in would otherwise poison a cache and produce
 * opaque 417s.
 *
 * This deliberately does not go through `page.evaluate(() => frappe.call(...))`:
 * a fixture that fails server-side would render an error dialog over the form and
 * the *next* assertion would fail with an unrelated message, and the request
 * would be invisible in the trace.
 */
export function createApi(page) {
    async function csrfToken() {
        const token = await page.evaluate(() => window.frappe?.csrf_token);

        if (!token)
            throw new Error(
                "No window.frappe.csrf_token: the page is not on the desk. " +
                    "Use the `desk` fixture, or gotoDesk(page), before calling the API.",
            );

        return token;
    }

    async function send(method, path, options = {}) {
        const response = await page.request[method](path, {
            ...options,
            headers: {
                Accept: "application/json",
                "Content-Type": "application/json",
                "X-Frappe-CSRF-Token": await csrfToken(),
                ...options.headers,
            },
        });

        if (!response.ok())
            throw new Error(
                `${method.toUpperCase()} ${path} -> ${response.status()}\n${await response.text()}`,
            );

        return response.json();
    }

    return {
        /** cy.call() — returns the unwrapped `message`. */
        async call(method, args = {}) {
            return (await send("post", `/api/method/${method}`, { data: args })).message;
        },

        /** Shorthand for the india_compliance.tests.ui_test_helpers fixtures. */
        fixture(name, args = {}) {
            return this.call(`india_compliance.tests.ui_test_helpers.${name}`, args);
        },

        /** cy.insert_doc(). */
        async insertDoc(doctype, doc) {
            return (await send("post", `/api/resource/${doctype}`, { data: { doctype, ...doc } })).data;
        },

        /** cy.get_doc(). */
        async getDoc(doctype, name) {
            return (await send("get", `/api/resource/${doctype}/${encodeURIComponent(name)}`)).data;
        },

        /** cy.get_list(). */
        async getList(doctype, { fields = ["name"], filters = {}, limit = 100 } = {}) {
            const params = new URLSearchParams({
                fields: JSON.stringify(fields),
                filters: JSON.stringify(filters),
                limit_page_length: String(limit),
            });

            return (await send("get", `/api/resource/${doctype}?${params}`)).data;
        },
    };
}
