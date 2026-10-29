import frappe
from frappe.tests import IntegrationTestCase


class TestBankAccount(IntegrationTestCase):
    def setUp(self):
        self.bank_account = frappe.new_doc(
            "Bank Account",
            account_name="_Test IFSC Bank Account",
            bank="_Test IFSC Bank",
            ifsc_code=" sbin-0001 234 ",
        ).insert()

    def test_ifsc_code_workflow(self):
        self.assertEqual(self.bank_account.ifsc_code, "SBIN0001234")

        self.bank_account.ifsc_code = " "
        self.bank_account.save()
        self.assertEqual(self.bank_account.ifsc_code, "")

        self.bank_account.ifsc_code = None
        self.bank_account.save()
        self.assertIsNone(self.bank_account.ifsc_code)

        for ifsc_code in ("sbin12", "SBIN1001234", "SBIN000123", "SBIN0ABC12!", "HDFCO000001"):
            self.bank_account.reload()
            self.bank_account.ifsc_code = ifsc_code
            self.assertRaisesRegex(frappe.ValidationError, "IFSC Code .* is invalid", self.bank_account.save)
