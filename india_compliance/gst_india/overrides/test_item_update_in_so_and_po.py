import json

import frappe
from frappe.tests.utils import FrappeTestCase
from erpnext.controllers.accounts_controller import update_child_qty_rate

from india_compliance.gst_india.utils.tests import create_transaction

DATA = {
    "customer": "_Test Dummy",
    "item_code": "_Test Trading Goods 1",
    "qty": 1,
    "rate": 100,
    "is_in_state": 1,
}

ITEM_TO_BE_UPDATED = json.dumps(
    [{"item_code": "_Test Trading Goods 1", "qty": 1, "rate": 200}]
)

EXPECTED_TOTAL = 236


class TestItemUpdate(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

    def create_order(self, doctype):
        DATA["doctype"] = doctype
        doc = create_transaction(**DATA)
        return doc.name

    def test_so_and_po_after_item_update(self):

        for doctype in ["Sales Order", "Purchase Order"]:
            self.name = self.create_order(doctype)
            update_child_qty_rate(doctype, ITEM_TO_BE_UPDATED, self.name)
            doc = frappe.get_doc(doctype, self.name)
            doc = doc.as_dict()

            if EXPECTED_TOTAL != doc.base_grand_total:
                self.fail("Base Grand Total doesn't match")
