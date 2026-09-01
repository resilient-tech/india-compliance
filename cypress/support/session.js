// Login and desk bootstrap.
//
// Plain exported functions, not Cypress commands: there is no global namespace to collide
// with, so no prefix is needed.

const SUPPRESS_NOTIFICATIONS = "india_compliance.tests.ui_test_helpers.suppress_notifications";

const NOTIFICATION_KEYS = [
    "needs_audit_trail_notification",
    "needs_item_tax_template_notification",
    "needs_new_gst_category_notification",
];

export function bootstrap() {
    cy.login();
    cy.visit("/desk");
    cy.desk_ready();

    cy.window({ log: false }).then((win) => {
        const defaults = win.frappe.boot.sysdefaults || {};
        const outstanding = NOTIFICATION_KEYS.filter((key) => Number(defaults[key]));

        if (!outstanding.length) return;

        cy.call(SUPPRESS_NOTIFICATIONS);
        cy.reload();
        cy.desk_ready();
    });
}
