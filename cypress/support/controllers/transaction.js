import FormController from "./form";
import { place_of_supply_pattern } from "../test_records";

export default class TransactionController extends FormController {
    set_supplier(supplier) {
        this.set_link("supplier", supplier);

        return this.wait_for_settle();
    }

    set_bill_no(value) {
        return this.fill("bill_no", value || `UI-${Date.now().toString().slice(-10)}`, "Data");
    }

    add_item(item_code, { qty = 1, rate = 100 } = {}) {
        const items = this.grid("items");

        items.ensure_rows(1);
        items.set_link(1, "item_code", item_code);
        this.wait_for_settle();

        items.set(1, "qty", qty);
        items.set(1, "rate", rate);
        this.wait_for_settle();

        items.collapse_row(1);

        return this.wait_for_settle();
    }

    assert_place_of_supply_matches(gstin) {
        this.doc()
            .its("place_of_supply")
            .should("match", place_of_supply_pattern(gstin));

        return this;
    }

    assert_intra_state_tax_heads() {
        this.doc().should((doc) => {
            expect(doc.taxes_and_charges, "a GST tax template was applied").to.be.ok;

            const heads = doc.taxes.map((row) => row.account_head);
            expect(heads, "two tax rows").to.have.length(2);
            expect(heads.some((head) => /CGST/.test(head)), `CGST row in ${heads}`).to.be.true;
            expect(heads.some((head) => /SGST/.test(head)), `SGST row in ${heads}`).to.be.true;
            expect(heads.some((head) => /IGST/.test(head)), `no IGST row in ${heads}`).to.be.false;

            const [cgst, sgst] = doc.taxes;
            expect(cgst.rate, "CGST rate is set").to.be.greaterThan(0);
            expect(sgst.rate, "SGST rate equals CGST rate").to.eq(cgst.rate);
        });

        return this;
    }
}
