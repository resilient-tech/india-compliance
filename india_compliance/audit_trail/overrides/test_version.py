import re

import frappe
from frappe.tests.utils import FrappeTestCase, change_settings

from india_compliance.gst_india.utils.tests import create_sales_invoice


class TestVersion(FrappeTestCase):

    @change_settings("Accounts Settings", {"enable_audit_trail": 1})
    def test_validate_version_change_delete(self):
        doc = create_sales_invoice(do_not_submit=True)
        doc.items[0].qty = 2
        doc.save(ignore_version=False)
        doc.submit()

        version = frappe.get_doc(
            "Version", {"ref_doctype": doc.doctype, "docname": doc.name}
        )

        version.ref_doctype = "Address"

        self.assertRaisesRegex(
            frappe.ValidationError,
            re.compile(r"^(Cannot alter Versions of.*)"),
            version.save,
        )

        self.assertRaisesRegex(
            frappe.ValidationError,
            re.compile(r"^(Cannot alter Versions of.*)"),
            version.delete,
        )
