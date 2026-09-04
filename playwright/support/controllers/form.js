import { expect } from "@playwright/test";

import BaseController from "./base";
import { fieldInput, fillField, newForm, slug, tableField } from "../frappe";

class Grid {
    constructor(page, fieldname) {
        this.page = page;
        this.fieldname = fieldname;
        this.root = page.locator(`.frappe-control[data-fieldname="${fieldname}"]`);
    }

    rows() {
        return this.root.locator(".grid-row[data-idx]");
    }

    row(idx) {
        return this.root.locator(`.grid-row[data-idx="${idx}"]`);
    }

    async assertRowCount(count) {
        await expect(this.rows()).toHaveCount(count);

        return this;
    }

    async ensureRows(count) {
        for (let existing = await this.rows().count(); existing < count; existing++) {
            await this.root.locator(".grid-add-row").click();
            await expect(this.rows()).toHaveCount(existing + 1);
        }

        return this.assertRowCount(count);
    }

    async openRow(idx) {
        const row = this.row(idx);

        if (!(await row.evaluate((el) => el.classList.contains("grid-row-open"))))
            await row.locator(".btn-open-row").click();

        await expect(row).toHaveClass(/grid-row-open/);

        return this;
    }

    async collapseRow(idx) {
        await this.row(idx).locator(".grid-collapse-row").click();
        await expect(this.row(idx)).not.toHaveClass(/grid-row-open/);

        return this;
    }

    /** The row must be open for the Link control to exist, so open it first. */
    async setLink(idx, fieldname, value) {
        await this.openRow(idx);
        await fillField(this.row(idx), fieldname, value, "Link");

        return this;
    }

    /**
     * Set a plain (non-Link) field in a row via its inline cell editor. Opens the
     * row first: on a collapsed row the cell resolves to a read-only .static-area,
     * which fill() cannot write to.
     */
    async set(idx, fieldname, value) {
        await this.openRow(idx);

        const cell = this.cell(idx, fieldname);

        await cell.click();
        await cell.fill(String(value));
        await cell.blur();

        return this;
    }

    cell(idx, fieldname, fieldtype = "Data") {
        return tableField(this.page, this.fieldname, idx, fieldname, fieldtype);
    }
}

export default class FormController extends BaseController {
    constructor(page, doctype) {
        super(page);
        this.doctype = doctype;
    }

    async openNew() {
        await newForm(this.page, this.doctype);

        return this;
    }

    async open(name) {
        await this.page.goto(`/app/${slug(this.doctype)}/${encodeURIComponent(name)}`);
        await expect(this.page.locator("body")).toHaveAttribute("data-ajax-state", "complete");

        return this.waitForSettle();
    }

    async fill(fieldname, value, fieldtype = "Data") {
        await fillField(this.page, fieldname, value, fieldtype);

        return this;
    }

    async setLink(fieldname, value) {
        await fillField(this.page, fieldname, value, "Link");

        return this;
    }

    field(fieldname, fieldtype = "Data") {
        return fieldInput(this.page, fieldname, fieldtype);
    }

    grid(fieldname) {
        return new Grid(this.page, fieldname);
    }

    /** A JSON snapshot of cur_frm.doc, safe to assert on outside the page. */
    async doc() {
        return this.page.evaluate(() =>
            window.cur_frm ? JSON.parse(JSON.stringify(window.cur_frm.doc)) : null,
        );
    }

    /**
     * Poll cur_frm.doc until `pick` satisfies the matcher. Client scripts settle
     * the doc asynchronously (place_of_supply, taxes), so a single read races.
     *
     *   await form.docValue((doc) => doc.place_of_supply).toMatch(/^24-/);
     */
    docValue(pick, message) {
        return expect.poll(async () => pick((await this.doc()) || {}), { message });
    }

    async save() {
        const saved = this.page.waitForResponse(
            (response) =>
                response.url().includes("/api/method/frappe.desk.form.save.savedocs") &&
                response.request().method() === "POST",
        );

        await this.page.locator('.page-container:visible button[data-label="Save"]').first().click();

        const response = await saved;
        expect(response.status(), `savedocs: ${await response.text()}`).toBe(200);

        return this.waitForSettle();
    }

    async assertStatus(status) {
        await expect(
            this.page.locator('.page-container:visible [data-testid="page-status"]').first(),
        ).toContainText(status);

        return this;
    }
}
