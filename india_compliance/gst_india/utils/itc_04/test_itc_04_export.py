from frappe.tests.utils import FrappeTestCase
from erpnext.accounts.doctype.payment_reconciliation.test_payment_reconciliation import (
    create_fiscal_year,
)
from erpnext.controllers.tests.test_subcontracting_controller import get_rm_items
from erpnext.subcontracting.doctype.subcontracting_order.subcontracting_order import (
    make_subcontracting_receipt,
)
from erpnext.subcontracting.doctype.subcontracting_order.test_subcontracting_order import (
    create_subcontracting_order,
)

from india_compliance.gst_india.overrides.test_subcontracting_transaction import (
    create_purchase_order,
    create_subcontracting_data,
    make_stock_transfer_entry,
)
from india_compliance.gst_india.utils.itc_04.itc_04_export import download_itc_04_json

SERVICE_ITEM = {
    "item_code": "Subcontracted Service Item 1",
    "qty": 10,
    "rate": 100,
    "fg_item": "Subcontracted Item SA2",
    "fg_item_qty": 10,
}

response = {
    "data": {
        "gstin": "24AAQCA8719H1ZC",
        "fp": "182024",
        "table5A": [
            {
                "ctin": "24AABCR6898M1ZN",
                "jw_stcd": "24",
                "items": [
                    {
                        "o_chnum": "MAT-STE-00001",
                        "o_chdt": "10-01-2025",
                        "jw2_chdt": "10-01-2025",
                        "nat_jw": "Job Work",
                        "uqc": "NOS",
                        "qty": 10.0,
                        "desc": "Subcontracted Item SA2",
                    }
                ],
                "flag": "N",
            }
        ],
        "m2jw": [
            {
                "jw_stcd": "24",
                "itms": [
                    {
                        "uqc": "NOS",
                        "qty": 10.0,
                        "desc": "Subcontracted SRM Item 1",
                        "txval": 200.0,
                        "goods_ty": "8b",
                        "tx_i": 0.0,
                        "tx_c": 0.0,
                        "tx_s": 0.0,
                        "tx_cs": 0.0,
                    },
                ],
                "chnum": "MAT-STE-00001",
                "chdt": "10-01-2025",
                "flag": "N",
            }
        ],
    },
    "filename": "ITC-04-Gov-24AAQCA8719H1ZC-182024.json",
    "has_invalid_data": False,
}


class TestITC04Export(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        create_fiscal_year(
            "_Test Indian Registered Company", "2024-04-01", "2025-03-31"
        )
        create_subcontracting_data()

        po = create_purchase_order(
            **SERVICE_ITEM,
            supplier_warehouse="Finished Goods - _TIRC",
            transaction_date="2025-01-07",
            do_no_submit=1,
        )
        po.schedule_date = "2025-01-10"
        po.save()
        po.submit()

        sco = create_subcontracting_order(po_name=po.name)

        rm_items = get_rm_items(sco.supplied_items)
        cls.se = make_stock_transfer_entry(
            sco_no=sco.name, rm_items=rm_items, do_not_submit=1
        )
        cls.se.posting_date = "2025-01-10"
        cls.se.set_posting_time = 1
        cls.se.save()
        cls.se.submit()

        cls.scr = make_subcontracting_receipt(sco.name)
        cls.scr.update({"posting_date": "2025-01-10", "set_posting_time": 1})
        cls.scr.save()

        cls.scr.append(
            "doc_references",
            {"link_doctype": "Stock Entry", "link_name": cls.se.name},
        )
        cls.scr.submit()

    def test_itc_04_export(self):
        data = download_itc_04_json(
            {
                "company": self.scr.company,
                "company_gstin": self.scr.company_gstin,
                "from_date": "2024-12-15",
                "to_date": "2025-02-20",
            }
        )
        self.assertDictEqual(response, data)

        data = download_itc_04_json(
            {
                "company": self.scr.company,
                "company_gstin": self.scr.company_gstin,
                "from_date": "2024-05-15",
                "to_date": "2025-02-20",
            }
        )

        self.assertEqual(data["data"]["fp"], "192024")
        self.assertEqual(data["filename"], "ITC-04-Gov-24AAQCA8719H1ZC-192024.json")
