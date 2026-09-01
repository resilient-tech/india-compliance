import BaseController from "./base";

class Grid {
    constructor(fieldname) {
        this.fieldname = fieldname;
        this.selector = `.frappe-control[data-fieldname="${fieldname}"]`;
    }

    rows() {
        return cy.get(`${this.selector} .grid-row[data-idx]`);
    }

    row(idx) {
        return cy.get(`${this.selector} .grid-row[data-idx="${idx}"]`);
    }

    assert_row_count(count) {
        this.rows().should("have.length", count);

        return this;
    }

    ensure_rows(count) {
        cy.get(this.selector).then(($grid) => {
            const existing = $grid.find(".grid-row[data-idx]").length;
            for (let i = existing; i < count; i++) {
                cy.get(`${this.selector} .grid-add-row`).click();
            }
        });

        return this.assert_row_count(count);
    }

    open_row(idx) {
        this.row(idx).then(($row) => {
            if (!$row.hasClass("grid-row-open")) {
                cy.wrap($row).find(".btn-open-row").click();
            }
        });
        this.row(idx).should("have.class", "grid-row-open");

        return this;
    }

    collapse_row(idx) {
        cy.get(`${this.selector} .grid-row[data-idx="${idx}"] .grid-collapse-row`).click();

        return this;
    }

    set_link(idx, fieldname, value) {
        this.open_row(idx);
        this.row(idx).within(() => {
            cy.fill_field(fieldname, value, "Link");
        });

        return this;
    }

    /** Set a plain (non-Link) field in a row via its inline cell editor. */
    set(idx, fieldname, value) {
        cy.get_table_field(this.fieldname, idx, fieldname).clear().type(String(value)).blur();

        return this;
    }

    cell(idx, fieldname) {
        return cy.get_table_field(this.fieldname, idx, fieldname);
    }
}

export default class FormController extends BaseController {
    constructor(doctype) {
        super();
        this.doctype = doctype;
    }

    open_new() {
        cy.new_form(this.doctype);

        return this;
    }

    open(name) {
        cy.visit(`/desk/${this.doctype.toLowerCase().replace(/ /g, "-")}/${encodeURIComponent(name)}`);
        cy.get("body").should("have.attr", "data-ajax-state", "complete");

        return this;
    }

    fill(fieldname, value, fieldtype = "Data") {
        cy.fill_field(fieldname, value, fieldtype);

        return this;
    }

    set_link(fieldname, value) {
        cy.fill_field(fieldname, value, "Link");

        return this;
    }

    field(fieldname, fieldtype = "Data") {
        return cy.get_field(fieldname, fieldtype);
    }

    grid(fieldname) {
        return new Grid(fieldname);
    }

    
    doc() {
        return cy.window({ log: false }).its("cur_frm.doc");
    }

    save() {
        cy.intercept("POST", "**/api/method/frappe.desk.form.save.savedocs").as("savedocs");
        cy.get('.page-container:visible button[data-label="Save"]').click({ force: true });
        cy.wait("@savedocs").its("response.statusCode").should("eq", 200);

        return this;
    }

    assert_status(status) {
        cy.get('[data-testid="page-status"]').should("contain", status);

        return this;
    }
}
