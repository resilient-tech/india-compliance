import frappe
from frappe.tests import IntegrationTestCase

from india_compliance.audit_trail.report.audit_trail.audit_trail import execute
from india_compliance.gst_india.utils.tests import create_sales_invoice


class TestAuditTrailReport(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.db.set_single_value("Accounts Settings", "enable_audit_trail", 1)
        cls.invoice = create_sales_invoice()

    @classmethod
    def tearDownClass(cls):
        frappe.db.set_single_value("Accounts Settings", "enable_audit_trail", 0)
        super().tearDownClass()

    def get_filters(self, report):
        return {
            "report": report,
            "company": "_Test Indian Registered Company",
            "doctype": "Sales Invoice",
            "date_option": "Custom",
            "date_range": ["2000-01-01", frappe.utils.today()],
        }

    def test_summary_by_doctype(self):
        _columns, data = execute(self.get_filters("Summary by DocType"))
        row = next(r for r in data if r["doctype"] == "Sales Invoice")
        self.assertGreaterEqual(row["new_count"], 1)

    def test_summary_by_user(self):
        _columns, data = execute(self.get_filters("Summary by User"))
        row = next(r for r in data if r["user_name"] == self.invoice.owner)
        self.assertGreaterEqual(row["new_count"], 1)

    def test_detailed(self):
        _columns, data = execute(self.get_filters("Detailed"))
        names = [r["document_name"] for r in data]
        self.assertIn(self.invoice.name, names)
