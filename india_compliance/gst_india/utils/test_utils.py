from datetime import date
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import getdate


class TestUtils(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.db.savepoint("before_test_utils")

        # create old fiscal years
        fiscal_year = frappe.new_doc("Fiscal Year")
        fiscal_year.update(
            {
                "year_start_date": "2023-04-01",
                "year_end_date": "2024-03-31",
                "year": "2023-2024",
            }
        ).insert(ignore_if_duplicate=True)

        fiscal_year = frappe.new_doc("Fiscal Year")
        fiscal_year.update(
            {
                "year_start_date": "2022-04-01",
                "year_end_date": "2023-03-31",
                "year": "2022-2023",
            }
        ).insert(ignore_if_duplicate=True)

        # Restricted user for permission boundary tests
        cls.restricted_user = "test_no_perms@example.com"
        if not frappe.db.exists("User", cls.restricted_user):
            frappe.get_doc(
                {
                    "doctype": "User",
                    "email": cls.restricted_user,
                    "first_name": "Test",
                    "send_welcome_email": 0,
                }
            ).insert(ignore_permissions=True)

        # User with Purchase Manager role (has Supplier read access)
        cls.purchase_user = "test_purchase_mgr@example.com"
        if not frappe.db.exists("User", cls.purchase_user):
            frappe.get_doc(
                {
                    "doctype": "User",
                    "email": cls.purchase_user,
                    "first_name": "Purchase",
                    "send_welcome_email": 0,
                    "roles": [{"role": "Purchase Manager"}],
                }
            ).insert(ignore_permissions=True)

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        frappe.db.rollback(save_point="before_test_utils")

    @patch("india_compliance.gst_india.utils.getdate", return_value=getdate("2023-06-20"))
    def test_timespan_date_range(self, getdate_mock):
        from india_compliance.gst_india.utils import get_timespan_date_range

        timespan_date_range_map = {
            "this fiscal year": (date(2023, 4, 1), date(2024, 3, 31)),
            "last fiscal year": (date(2022, 4, 1), date(2023, 3, 31)),
            "this fiscal year to last month": (date(2023, 4, 1), date(2023, 5, 31)),
            "this quarter to last month": (date(2023, 4, 1), date(2023, 5, 31)),
        }

        for timespan, expected_date_range in timespan_date_range_map.items():
            actual_date_range = get_timespan_date_range(timespan)

            for i, expected_date in enumerate(expected_date_range):
                self.assertEqual(expected_date, actual_date_range[i])

    def test_get_gstin_list_with_ephemeral_document(self):
        """get_gstin_list should return empty list for unsaved (ephemeral) documents."""
        from india_compliance.gst_india.utils import get_gstin_list

        original_user = frappe.session.user
        try:
            frappe.set_user("Administrator")
            result = get_gstin_list("new-supplier-1", "Supplier")
            self.assertEqual(result, [])
        finally:
            frappe.set_user(original_user)

    def test_get_gstin_list_returns_list_for_saved_document(self):
        """get_gstin_list should return a list (not raise) for a real saved Supplier."""
        from india_compliance.gst_india.utils import get_gstin_list

        original_user = frappe.session.user
        try:
            frappe.set_user(self.purchase_user)
            # Uses a Supplier fixture defined in india_compliance/tests/test_records.json
            result = get_gstin_list("_Test Registered Supplier", "Supplier")
            self.assertIsInstance(result, list)
        finally:
            frappe.set_user(original_user)

    def test_get_gstin_list_raises_permission_error_for_restricted_user(self):
        """get_gstin_list should raise PermissionError for users without doctype access."""
        from india_compliance.gst_india.utils import get_gstin_list

        original_user = frappe.session.user
        try:
            frappe.set_user(self.restricted_user)
            self.assertRaises(frappe.PermissionError, get_gstin_list, "new-supplier-1", "Supplier")
        finally:
            frappe.set_user(original_user)

    def test_make_default_tax_templates_raises_permission_error_for_restricted_user(self):
        """make_default_tax_templates should raise PermissionError for users without write access."""
        from india_compliance.gst_india.overrides.company import make_default_tax_templates

        original_user = frappe.session.user
        try:
            frappe.set_user(self.restricted_user)
            self.assertRaises(frappe.PermissionError, make_default_tax_templates, "new-company-1")
        finally:
            frappe.set_user(original_user)
