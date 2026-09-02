import { test } from "../support/fixtures";
import TransactionController from "../support/controllers/transaction";
import { getRecord } from "../support/test_records";

// Supplier and company are both in state 24, which is what makes the intra-state
// expectation below true.
const company = getRecord("Company", "_Test Indian Registered Company");
const supplier = getRecord("Supplier", "_Test Registered Supplier");
const item = getRecord("Item", "_Test Trading Goods 1");

test.describe("Purchase Invoice", () => {
    test("applies in-state GST when the supplier is in the company's state", async ({ desk }) => {
        const form = new TransactionController(desk, "Purchase Invoice");

        await form.openNew();

        await form.setSupplier(supplier.name);
        await form.setBillNo();
        await form.addItem(item.name);

        await form.assertPlaceOfSupplyMatches(company.gstin);
        await form.assertIntraStateTaxHeads();

        await form.save();
        await form.assertStatus("Draft");
    });
});
