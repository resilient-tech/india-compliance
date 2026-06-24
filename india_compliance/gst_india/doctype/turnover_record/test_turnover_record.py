# Copyright (c) 2026, Resilient Tech and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from india_compliance.gst_india.doctype.turnover_record.turnover_record import upsert_turnover_record
from india_compliance.gst_india.utils.isd import get_distribution_addresses
from india_compliance.tests.erpnext_test_utils import create_fiscal_year

_POSTING_DATE = "2025-07-01"
_FY_START, _FY_END = "2025-04-01", "2026-03-31"
_STATE = "Karnataka"
_GSTIN = "29AAACI1681G1ZL"  # valid Karnataka GSTIN


class IntegrationTestTurnoverRecord(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        create_fiscal_year("_Test Indian Registered Company", _FY_START, _FY_END)

        cls.customer = "_Test TR Customer"
        if not frappe.db.exists("Customer", cls.customer):
            frappe.get_doc(
                {
                    "doctype": "Customer",
                    "customer_name": cls.customer,
                    "customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
                    "territory": frappe.db.get_value("Territory", {"is_group": 0}, "name"),
                }
            ).insert(ignore_permissions=True)

        addr_title = "_Test TR Karnataka Address"
        cls.address = frappe.db.get_value("Address", {"address_title": addr_title}, "name")
        if not cls.address:
            cls.address = (
                frappe.get_doc(
                    {
                        "doctype": "Address",
                        "address_title": addr_title,
                        "address_type": "Billing",
                        "address_line1": "Line 1",
                        "city": "Bengaluru",
                        "state": _STATE,
                        "pincode": "560001",
                        "country": "India",
                        "gstin": _GSTIN,
                        "gst_category": "Registered Regular",
                        "links": [{"link_doctype": "Customer", "link_name": cls.customer}],
                    }
                )
                .insert(ignore_permissions=True)
                .name
            )

    def setUp(self):
        # tests share the same state/period; isolate each from the others' records
        frappe.db.delete("Turnover Record", {"from_date": _FY_START, "to_date": _FY_END})

    def _state_records(self):
        return frappe.get_all(
            "Turnover Record",
            filters={"gst_state": _STATE, "from_date": _FY_START, "to_date": _FY_END},
            fields=["name", "gstin", "amount"],
        )

    def test_upsert_is_per_state_single_record(self):
        """A state has a single branch: repeated upserts for the same state collapse to one record
        (the amount is updated in place, not duplicated)."""
        upsert_turnover_record(gstin=_GSTIN, gst_state=_STATE, amount=1000, posting_date=_POSTING_DATE)
        upsert_turnover_record(gstin="", gst_state=_STATE, amount=3000, posting_date=_POSTING_DATE)

        records = self._state_records()
        self.assertEqual(len(records), 1)
        self.assertEqual(flt(records[0].amount), 3000)

    def test_get_distribution_addresses_resolves_state_turnover(self):
        """A registered address resolves its state's turnover (the join must be by state, not gstin)."""
        upsert_turnover_record(gstin=_GSTIN, gst_state=_STATE, amount=4000, posting_date=_POSTING_DATE)

        rows = get_distribution_addresses("Customer", self.customer, _POSTING_DATE, address=self.address)
        self.assertEqual(len(rows), 1)
        self.assertEqual(flt(rows[0].turnover_amount), 4000)

    def test_gst_state_derived_from_gstin(self):
        """gst_state is set from the gstin on the backend (need not be passed for a registered branch)."""
        doc = frappe.get_doc(
            {
                "doctype": "Turnover Record",
                "from_date": _FY_START,
                "to_date": _FY_END,
                "gstin": _GSTIN,
                "amount": 500,
            }
        ).insert(ignore_permissions=True)

        self.assertEqual(doc.gst_state, "Karnataka")

    def test_gst_state_mismatch_with_gstin_is_rejected(self):
        """A gst_state that contradicts the gstin is rejected."""
        doc = frappe.get_doc(
            {
                "doctype": "Turnover Record",
                "from_date": _FY_START,
                "to_date": _FY_END,
                "gstin": _GSTIN,  # Karnataka
                "gst_state": "Gujarat",
                "amount": 500,
            }
        )
        self.assertRaises(frappe.ValidationError, doc.insert)

    def test_duplicate_record_for_same_state_and_period_is_rejected(self):
        """A second record for the same state + overlapping period is rejected; re-saving the same
        record is allowed (it must not flag itself)."""
        first = frappe.get_doc(
            {
                "doctype": "Turnover Record",
                "from_date": _FY_START,
                "to_date": _FY_END,
                "gstin": _GSTIN,
                "gst_state": _STATE,
                "amount": 1000,
            }
        ).insert(ignore_permissions=True)

        first.amount = 2000
        first.save(ignore_permissions=True)

        duplicate = frappe.copy_doc(first)
        self.assertRaises(frappe.ValidationError, duplicate.insert)

    def test_changing_saved_record_state_to_existing_one_is_rejected(self):
        """A saved record whose state is later changed to one that already has a record is rejected
        on save (collision with a different record)."""
        existing = frappe.get_doc(
            {
                "doctype": "Turnover Record",
                "from_date": _FY_START,
                "to_date": _FY_END,
                "gst_state": "Gujarat",
                "amount": 1000,
            }
        ).insert(ignore_permissions=True)

        other = frappe.copy_doc(existing)
        other.gst_state = "Karnataka"
        other.amount = 2000
        other.insert(ignore_permissions=True)

        other.gst_state = "Gujarat"
        self.assertRaises(frappe.ValidationError, other.save)
