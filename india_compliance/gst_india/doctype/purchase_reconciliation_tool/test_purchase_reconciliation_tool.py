# Copyright (c) 2022, Resilient Tech and Contributors
# See license.txt
import ast

import frappe
from frappe.test_runner import make_test_objects
from frappe.tests.utils import FrappeTestCase

from india_compliance.gst_india.doctype.gst_inward_supply.gst_inward_supply import (
    create_inward_supply,
)
from india_compliance.gst_india.utils.tests import create_purchase_invoice


class TestPurchaseReconciliationTool(FrappeTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()

        cls.test_records = frappe.get_file_json(
            frappe.get_app_path(
                "india_compliance",
                "gst_india",
                "data",
                "test_purchase_reconciliation.json",
            )
        )

        create_test_records(cls.test_records)

    def test_get_data_for_exact_match(self):
        exact_match_records = self.test_records.get("Exact Match")
        create_inward_supply(frappe._dict(exact_match_records.get("Inward Supply")))

        create_purchase_invoice(
            **exact_match_records.get("Purchase Invoice"),
        )

        self.reco_data = update_purchase_reconciliation()
        self.reco_data.save()

        self.assertListEqual(
            ast.literal_eval(self.reco_data.reconciliation_data),
            exact_match_records.get("reconciliation_data"),
        )


def create_test_records(test_records):
    for doctype, data in test_records.items():
        if doctype in ("Supplier", "Address"):
            make_test_objects(doctype, data, reset=True)


def update_purchase_reconciliation():
    doc = frappe.get_doc("Purchase Reconciliation Tool")
    doc.update(
        {
            "company": "_Test Indian Registered Company",
            "company_gstin": "24AAQCA8719H1ZC",
            "gst_return": "GSTR 2B",
            "purchase_from_date": "2023-10-01",
            "purchase_to_date": "2023-10-31",
            "inward_supply_from_date": "2023-10-01",
            "inward_supply_to_date": "2023-10-31",
            "include_ignored": 0,
        }
    )

    return doc
