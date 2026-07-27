import frappe
from frappe.tests import IntegrationTestCase

from india_compliance.gst_india.utils.itc_04.itc_04_data import ITC04Query


class TestITC04Query(IntegrationTestCase):
    def test_init_sets_filters(self):
        query = ITC04Query(frappe._dict(company="_Test Company"))
        self.assertEqual(query.filters.company, "_Test Company")
        self.assertIsNotNone(query.se)
        self.assertIsNotNone(query.se_item)
        self.assertIsNotNone(query.sr)
        self.assertIsNotNone(query.sr_item)
        self.assertIsNotNone(query.ref_doc)

    def test_init_empty_filters(self):
        query = ITC04Query()
        self.assertEqual(query.filters, frappe._dict())

    def test_init_sets_doctype_wrappers(self):
        query = ITC04Query()
        self.assertEqual(str(query.se_doctype), "'Stock Entry'")
        self.assertEqual(str(query.sr_doctype), "'Subcontracting Receipt'")
