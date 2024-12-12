import re

import frappe
<<<<<<< HEAD
from frappe.tests.utils import FrappeTestCase
=======
from frappe.tests import IntegrationTestCase
>>>>>>> 159ed757 (test: additionally test gst details for credit note with zero value)

from india_compliance.gst_india.utils.tests import create_sales_invoice


<<<<<<< HEAD
class TestVersion(FrappeTestCase):
=======
class TestVersion(IntegrationTestCase):
>>>>>>> 159ed757 (test: additionally test gst details for credit note with zero value)
    def test_validate_version_where_audit_trail_enabled(self):
        # enable audit trail
        frappe.db.set_single_value("Accounts Settings", "enable_audit_trail", 1)

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

        # disable audit trail
        frappe.db.set_single_value("Accounts Settings", "enable_audit_trail", 0)

    def test_validate_version_where_audit_trail_disabled(self):
        doc = create_sales_invoice(do_not_submit=True)
        doc.items[0].qty = 2
        doc.save(ignore_version=False)
        doc.submit()

        version = frappe.get_doc(
            "Version", {"ref_doctype": doc.doctype, "docname": doc.name}
        )

        version.ref_doctype = "Address"

        version.save()
        version.delete()
