import { expect } from "@playwright/test";

import { deskReady } from "../frappe";

export default class BaseController {
    /** @param {import("@playwright/test").Page} page */
    constructor(page) {
        this.page = page;
    }

    async waitForSettle() {
        await deskReady(this.page);

        return this;
    }

    async assertNoModal() {
        await expect(this.page.locator(".modal:visible")).toHaveCount(0);

        return this;
    }
}
