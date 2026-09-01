import TransactionController from "../support/controllers/transaction";
import { bootstrap } from "../support/session";
import { get } from "../support/test_records";

describe("Purchase Invoice", () => {
    const page = new TransactionController("Purchase Invoice");

    // Supplier and company are both in state 24, which is what makes the intra-state
    // expectation below true.
    const company = get("Company", "_Test Indian Registered Company");
    const supplier = get("Supplier", "_Test Registered Supplier");
    const item = get("Item", "_Test Trading Goods 1");

    before(() => {
        bootstrap();
    });

    it("applies in-state GST when the supplier is in the company's state", () => {
        page.open_new();

        page.set_supplier(supplier.name);
        page.set_bill_no();
        page.add_item(item.name);

        page.assert_place_of_supply_matches(company.gstin);
        page.assert_intra_state_tax_heads();

        page.save();
        page.assert_status("Draft");
    });

});
