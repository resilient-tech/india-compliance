from frappe.tests.utils import FrappeTestCase

from india_compliance.gst_india.utils.tests import create_transaction


class TestSubcontractingTransaction(FrappeTestCase):
    def test_create_and_update_stock_entry(self):
        # Create a subcontracting transaction
        args = {
            "stock_entry_type": "Send to Subcontractor",
            "purpose": "Send to Subcontractor",
            "bill_from_address": "_Test Indian Registered Company-Billing",
            "bill_to_address": "_Test Registered Supplier-Billing",
            "items": [
                {
                    "item_code": "_Test Trading Goods 1",
                    "qty": 1,
                    "gst_hsn_code": "61149090",
                    "s_warehouse": "Finished Goods - _TIRC",
                    "t_warehouse": "Goods In Transit - _TIRC",
                    "amount": 100,
                    "taxable_value": 100,
                }
            ],
            "company": "_Test Indian Registered Company",
            "base_grand_total": 100,
        }

        stock_entry = self._create_stock_entry(args)

        # Update the subcontracting transaction
        stock_entry.run_method("onload")  # update virtual fields
        stock_entry.select_print_heading = "Credit Note"
        stock_entry.save()

        self.assertEqual(stock_entry.select_print_heading, "Credit Note")

    def _create_stock_entry(self, doc_args):
        """Generate Stock Entry to test e-Waybill functionalities"""
        doc_args.update({"doctype": "Stock Entry"})

        stock_entry = create_transaction(**doc_args)
        return stock_entry
