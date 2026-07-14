# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days

from india_compliance.gst_india.utils.tests import create_purchase_invoice
from india_compliance.income_tax_india.constants import MSME_PAYMENT_DAYS
from india_compliance.income_tax_india.doctype.msme_registration.test_msme_registration import (
    create_msme_registration,
    create_supplier,
)
from india_compliance.income_tax_india.overrides.purchase_invoice import (
    get_msme_details,
    get_valid_msme_registrations,
)

COMPANY = "_Test Indian Registered Company"
POSTING_DATE = "2023-05-01"
FY = "2023-2024"

DUE_DATE_ADVISORY = "Invalid Due Date"
CANCELLED_ADVISORY = "MSME Registration Cancelled"
NOT_APPLICABLE_ADVISORY = "MSME Registration Not Applicable"


class TestMSMEPaymentTerms(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        frappe.db.savepoint("before_test_msme_payment_terms")

    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback(save_point="before_test_msme_payment_terms")

    def test_advisory_shown_beyond_45_days(self):
        supplier = self._create_supplier(enterprise_type="Micro")
        self.assertAdvisory(supplier, days=MSME_PAYMENT_DAYS + 1, shown=True)

    def test_no_advisory_on_the_45th_day(self):
        supplier = self._create_supplier(enterprise_type="Micro")
        self.assertAdvisory(supplier, days=MSME_PAYMENT_DAYS, shown=False)

    def test_no_advisory_for_trader(self):
        supplier = self._create_supplier(enterprise_type="Micro", activity="Trading")
        self.assertAdvisory(supplier, days=MSME_PAYMENT_DAYS + 30, shown=False)

    def test_no_advisory_for_medium_enterprise(self):
        supplier = self._create_supplier(enterprise_type="Medium")
        self.assertAdvisory(supplier, days=MSME_PAYMENT_DAYS + 30, shown=False)

    def test_no_advisory_when_unclassified_for_the_year(self):
        # classified for a different FY than the invoice's
        supplier = self._create_supplier(enterprise_type="Micro", financial_year="2024-2025")
        self.assertAdvisory(supplier, days=MSME_PAYMENT_DAYS + 30, shown=False)

    def test_cancelled_registration_is_advised(self):
        supplier = self._create_cancelled_supplier(cancelled_on=add_days(POSTING_DATE, -1))
        pi = self._get_purchase_invoice(supplier, days=10)

        self.assertTrue(self._get_advisory(pi, CANCELLED_ADVISORY))
        self.assertEqual(pi.docstatus, 0)  # advisory only: the invoice still saves

    def test_no_cancellation_advisory_on_the_cancellation_date(self):
        """A supply accepted on the cancellation date is still covered."""
        supplier = self._create_cancelled_supplier(cancelled_on=POSTING_DATE)
        pi = self._get_purchase_invoice(supplier, days=10)

        self.assertFalse(self._get_advisory(pi, CANCELLED_ADVISORY))

    def test_no_cancellation_advisory_for_active_registration(self):
        supplier = self._create_supplier(enterprise_type="Micro")
        pi = self._get_purchase_invoice(supplier, days=10)

        self.assertFalse(self._get_advisory(pi, CANCELLED_ADVISORY))

    def test_cancellation_supersedes_the_due_date_advisory(self):
        """A cancelled registration is not MSME, so the 45-day limit no longer applies."""
        supplier = self._create_cancelled_supplier(cancelled_on=add_days(POSTING_DATE, -1))
        pi = self._get_purchase_invoice(supplier, days=MSME_PAYMENT_DAYS + 30)

        frappe.message_log.clear()
        pi.save()

        titles = [frappe.parse_json(message).get("title") for message in frappe.message_log]
        self.assertIn(CANCELLED_ADVISORY, titles)
        self.assertNotIn(DUE_DATE_ADVISORY, titles)

    def test_advisory_when_invoice_predates_the_registration(self):
        """A backdated invoice cannot claim a registration that did not exist yet."""
        msme = create_msme_registration(
            registration_date=add_days(POSTING_DATE, 1),
            classifications=[{"financial_year": FY, "enterprise_type": "Micro"}],
        )
        pi = self._get_purchase_invoice(create_supplier(msme.name), days=10)

        self.assertTrue(self._get_advisory(pi, NOT_APPLICABLE_ADVISORY))

    def test_only_valid_registrations_are_selectable(self):
        """The link field must not offer a registration that did not cover the supply."""
        msme = create_msme_registration(
            registration_date="2023-04-01",
            classifications=[{"financial_year": FY, "enterprise_type": "Micro"}],
        )
        msme.mark_as_cancelled("2023-10-15")

        self.assertFalse(self._is_selectable(msme.name, "2023-03-01"))  # before registration
        self.assertTrue(self._is_selectable(msme.name, "2023-06-01"))  # while valid
        self.assertTrue(self._is_selectable(msme.name, "2023-10-15"))  # on cancellation date
        self.assertFalse(self._is_selectable(msme.name, "2023-11-01"))  # after cancellation

    def test_active_registration_is_always_selectable(self):
        """cancelled_date is NULL when active, which a plain date filter would exclude."""
        msme = create_msme_registration(
            registration_date="2023-04-01",
            classifications=[{"financial_year": FY, "enterprise_type": "Micro"}],
        )

        self.assertTrue(self._is_selectable(msme.name, "2023-06-01"))
        self.assertTrue(self._is_selectable(msme.name, "2030-01-01"))

    def _is_selectable(self, msme_registration, posting_date):
        registrations = get_valid_msme_registrations(
            "MSME Registration", "", "name", 0, 50, {"posting_date": posting_date}
        )
        return msme_registration in [row[0] for row in registrations]

    def test_registration_can_be_cleared_on_the_invoice(self):
        """The field is editable: a cleared value must not be refetched on save."""
        supplier = self._create_supplier(enterprise_type="Micro")
        pi = self._get_purchase_invoice(supplier, days=MSME_PAYMENT_DAYS + 30)
        self.assertTrue(pi.msme_registration)

        pi.msme_registration = None
        pi.save()

        self.assertFalse(pi.msme_registration)

    def test_advisory_keys_off_the_last_instalment(self):
        """A schedule paid in parts is late only if the final instalment is."""
        supplier = self._create_supplier(enterprise_type="Micro")
        pi = self._get_purchase_invoice(supplier, days=10)

        pi.payment_schedule = []
        for days, amount in ((10, 400), (MSME_PAYMENT_DAYS + 10, 600)):
            pi.append(
                "payment_schedule",
                {"due_date": add_days(POSTING_DATE, days), "payment_amount": amount},
            )

        self.assertTrue(self._get_advisory(pi))

    def assertAdvisory(self, supplier, days, shown):
        messages = self._get_advisory(self._get_purchase_invoice(supplier, days))
        self.assertEqual(bool(messages), shown)

    def _get_advisory(self, doc, title=DUE_DATE_ADVISORY):
        frappe.message_log.clear()
        doc.save()

        return [message for message in frappe.message_log if frappe.parse_json(message).get("title") == title]

    def _get_purchase_invoice(self, supplier, days):
        return create_purchase_invoice(
            supplier=supplier,
            company=COMPANY,
            posting_date=POSTING_DATE,
            set_posting_time=1,
            payment_terms_template=None,
            due_date=add_days(POSTING_DATE, days),
            # seeded from the supplier by the client script, not fetch_from
            msme_registration=get_msme_details({"supplier": supplier})["msme_registration"],
            qty=1,
            rate=1000,
            do_not_submit=True,
        )

    def _create_supplier(self, enterprise_type, activity=None, financial_year=FY):
        classification = {"financial_year": financial_year, "enterprise_type": enterprise_type}
        if activity:
            classification["activity"] = activity

        return create_supplier(create_msme_registration(classifications=[classification]).name)

    def _create_cancelled_supplier(self, cancelled_on):
        msme = create_msme_registration(classifications=[{"financial_year": FY, "enterprise_type": "Micro"}])
        msme.mark_as_cancelled(cancelled_on)

        return create_supplier(msme.name)
