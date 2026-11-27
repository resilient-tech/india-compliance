import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import today

from india_compliance.income_tax_india.constants import MSME_PAYMENT_TERMS_TEMPLATE
from india_compliance.income_tax_india.doctype.msme_registration.test_msme_registration import (
    create_msme_registration,
)
from india_compliance.income_tax_india.setup import create_msme_payment_terms_template
from india_compliance.income_tax_india.utils.msme import (
    get_indian_fiscal_year,
    get_msme_registration_for_pan,
)


class TestSupplierOverride(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        frappe.db.savepoint("before_test_income_tax_supplier")
        create_msme_payment_terms_template()

    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback(save_point="before_test_income_tax_supplier")

    def test_msme_payment_terms_template(self):
        create_msme_payment_terms_template()

        terms = frappe.get_doc("Payment Terms Template", MSME_PAYMENT_TERMS_TEMPLATE).terms
        self.assertEqual(
            [(row.invoice_portion, row.due_date_based_on, row.credit_days) for row in terms],
            [(100, "Day(s) after invoice date", 45)],
        )

    def test_msme_payment_terms_message(self):
        micro = self.create_registration("Micro")
        group = frappe.db.get_value("Supplier Group", {"is_group": 0})

        self.assertTrue(self.saved_with_message(self.new_supplier(micro, group)))
        self.assertTrue(self.saved_with_message(self.new_supplier(micro, group, terms_template(60))))
        self.assertTrue(
            self.saved_with_message(
                self.new_supplier(
                    micro, group, terms_template(30, "Day(s) after the end of the invoice month")
                )
            )
        )
        self.assertFalse(
            self.saved_with_message(self.new_supplier(micro, group, MSME_PAYMENT_TERMS_TEMPLATE))
        )
        self.assertFalse(self.saved_with_message(self.new_supplier(micro, group, terms_template(30))))

        for enterprise_type, activity in (("Medium", "Manufacturing"), ("Small", "Trading")):
            supplier = self.new_supplier(self.create_registration(enterprise_type, activity), group)
            self.assertFalse(self.saved_with_message(supplier))

        supplier = self.new_supplier(micro, group, MSME_PAYMENT_TERMS_TEMPLATE)
        supplier.insert()
        supplier.payment_terms = None
        self.assertTrue(self.saved_with_message(supplier))
        self.assertFalse(self.saved_with_message(supplier))

        frappe.db.set_value("Supplier Group", group, "payment_terms", terms_template(30))
        self.assertFalse(self.saved_with_message(self.new_supplier(micro, group)))

        [message] = self.get_messages(self.new_supplier(micro, group, terms_template(60)))
        self.assertEqual(message["primary_action"]["args"]["payment_terms"], MSME_PAYMENT_TERMS_TEMPLATE)

        frappe.delete_doc("Payment Terms Template", MSME_PAYMENT_TERMS_TEMPLATE, force=True)
        [message] = self.get_messages(self.new_supplier(micro, group, terms_template(60)))
        self.assertFalse(message.get("primary_action"))
        self.assertIn("Set Payment Terms of 45 days or less", message["message"])

    def test_msme_registration_offered_for_same_pan(self):
        group = frappe.db.get_value("Supplier Group", {"is_group": 0})
        self.assertIsNone(get_msme_registration_for_pan("AAAPL9001C"))

        micro = create_msme_registration(pan="AAAPL9001C").name
        self.assertEqual(get_msme_registration_for_pan("AAAPL9001C"), micro)

        supplier = self.new_supplier(None, group)
        supplier.pan = "AAAPL9001C"
        [message] = self.get_messages(supplier, "MSME Registration Found")
        self.assertEqual(message["primary_action"]["args"]["msme_registration"], micro)
        self.assertFalse(self.saved_with(supplier, "MSME Registration Found"))

        create_msme_registration(pan="AAAPL9001C")
        self.assertIsNone(get_msme_registration_for_pan("AAAPL9001C"))

    def test_msme_pan_mismatch_message(self):
        group = frappe.db.get_value("Supplier Group", {"is_group": 0})
        registration = create_msme_registration(pan="AAAPL9002C").name

        supplier = self.new_supplier(registration, group, MSME_PAYMENT_TERMS_TEMPLATE)
        supplier.pan = "AAAPL9003C"
        self.assertTrue(self.saved_with(supplier, "MSME PAN Mismatch"))
        self.assertFalse(self.saved_with(supplier, "MSME PAN Mismatch"))

        supplier.pan = "AAAPL9002C"
        self.assertFalse(self.saved_with(supplier, "MSME PAN Mismatch"))

    def create_registration(self, enterprise_type, activity="Manufacturing"):
        return create_msme_registration(
            classifications=[
                {
                    "financial_year": get_indian_fiscal_year(today()),
                    "enterprise_type": enterprise_type,
                    "activity": activity,
                }
            ]
        ).name

    def new_supplier(self, msme_registration, supplier_group, payment_terms=None):
        supplier = frappe.new_doc("Supplier")
        supplier.update(
            {
                "supplier_name": frappe.generate_hash(length=10),
                "supplier_group": supplier_group,
                "msme_registration": msme_registration,
                "payment_terms": payment_terms,
            }
        )
        return supplier

    def saved_with_message(self, supplier):
        return self.saved_with(supplier, "MSME Payment Terms")

    def saved_with(self, supplier, title):
        return bool(self.get_messages(supplier, title))

    def get_messages(self, supplier, title="MSME Payment Terms"):
        frappe.clear_messages()
        supplier.save()
        return [message for message in frappe.get_message_log() if message.get("title") == title]


def terms_template(credit_days, due_date_based_on="Day(s) after invoice date"):
    name = f"_Test MSME Terms {frappe.generate_hash(length=6)}"
    frappe.get_doc(
        {
            "doctype": "Payment Terms Template",
            "template_name": name,
            "terms": [
                {
                    "invoice_portion": 100,
                    "due_date_based_on": due_date_based_on,
                    "credit_days": credit_days,
                }
            ],
        }
    ).insert()
    return name
