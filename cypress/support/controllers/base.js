
export default class BaseController {
    wait_for_settle() {
        cy.window({ log: false }).should((win) => {
            expect(win.frappe && win.frappe.app, "desk booted").to.be.ok;
            expect(win.frappe.request.ajax_count, "requests settled").to.eq(0);
        });

        return this;
    }

    assert_no_modal() {
        cy.get(".modal:visible").should("not.exist");

        return this;
    }
}
