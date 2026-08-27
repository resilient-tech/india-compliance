# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days

from india_compliance.gst_india.utils.tests import create_purchase_invoice
from india_compliance.income_tax_india.doctype.msme_registration.test_msme_registration import (
    create_msme_registration,
    create_supplier,
)
from india_compliance.income_tax_india.overrides.party import get_msme_details
from india_compliance.income_tax_india.utils.msme import MSME_PAYMENT_DAYS, get_msme_registration_options

COMPANY = "_Test Indian Registered Company"
POSTING_DATE = "2023-05-01"
FY = "2023-2024"

DUE_DATE_ADVISORY = "Invalid Due Date"
INVALID_ADVISORY = "Invalid MSME Registration"


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

    def test_no_advisory_for_a_type_outside_43bh(self):
        for enterprise_type in ("Medium", "Not MSME"):
            supplier = self._create_supplier(enterprise_type=enterprise_type)
            self.assertAdvisory(supplier, days=MSME_PAYMENT_DAYS + 30, shown=False)

    def test_advisory_falls_back_to_45_days_when_unclassified(self):
        """A year with no classification is assumed covered, on the Act's outer
        limit - the same assumption the reports make.
        """
        # classified for a different FY than the invoice's
        supplier = self._create_supplier(enterprise_type="Micro", financial_year="2024-2025")

        self.assertAdvisory(supplier, days=MSME_PAYMENT_DAYS + 1, shown=True)
        self.assertAdvisory(supplier, days=MSME_PAYMENT_DAYS, shown=False)

    def test_a_registration_cancelled_before_the_supply_is_unset(self):
        supplier = self._create_cancelled_supplier(cancelled_on=add_days(POSTING_DATE, -1))
        pi = self._get_purchase_invoice(supplier, days=10)

        self.assertIsNone(pi.msme_registration)
        self.assertTrue(self._get_advisory(pi, INVALID_ADVISORY))
        self.assertEqual(pi.docstatus, 0)  # the invoice still saves

    def test_a_registration_cancelled_on_the_posting_date_is_kept(self):
        """A supply accepted on the cancellation date is still covered."""
        supplier = self._create_cancelled_supplier(cancelled_on=POSTING_DATE)
        pi = self._get_purchase_invoice(supplier, days=10)

        self.assertTrue(pi.msme_registration)

    def test_a_supply_predating_the_registration_is_unset(self):
        """A backdated invoice cannot claim a registration that did not exist yet."""
        msme = create_msme_registration(
            registration_date=add_days(POSTING_DATE, 1),
            classifications=[{"financial_year": FY, "enterprise_type": "Micro"}],
        )
        pi = self._get_purchase_invoice(create_supplier(msme.name), days=10)

        self.assertIsNone(pi.msme_registration)

    def test_unsetting_takes_the_due_date_advisory_with_it(self):
        """An unset registration is not MSME, so the 45-day limit no longer applies."""
        supplier = self._create_cancelled_supplier(cancelled_on=add_days(POSTING_DATE, -1))
        pi = self._get_purchase_invoice(supplier, days=MSME_PAYMENT_DAYS + 30)

        self.assertFalse(self._get_advisory(pi))

    def test_a_registration_that_did_not_apply_is_offered_with_the_reason(self):
        """The field is editable and the advisory only advises, so nothing is
        hidden - but the description says why it did not cover the supply.
        """
        msme = create_msme_registration(
            registration_date="2023-04-01",
            classifications=[{"financial_year": FY, "enterprise_type": "Micro"}],
        )
        msme.mark_as_cancelled("2023-10-15")

        self.assertEqual(self._get_selectable("2023-06-01")[msme.name], "Micro - Manufacturing")

        # the classification is shown either way, marked for the supplies it missed
        self.assertEqual(self._get_selectable("2023-11-01")[msme.name], "Micro - Manufacturing, Invalid")
        # 2023-03-01 falls in FY 2022-2023, which has no classification at all
        self.assertEqual(self._get_selectable("2023-03-01")[msme.name], "Invalid")

    def test_active_registration_is_always_selectable(self):
        """cancelled_date is NULL when active, which a plain date filter would exclude."""
        msme = create_msme_registration(
            registration_date="2023-04-01",
            classifications=[{"financial_year": FY, "enterprise_type": "Micro"}],
        )

        self.assertTrue(self._is_selectable(msme.name, "2023-06-01"))
        self.assertTrue(self._is_selectable(msme.name, "2030-01-01"))

    def test_renaming_a_registration_leaves_a_filed_invoice_alone(self):
        """The invoice holds the number as filed, not a link a rename rewrites."""
        supplier = self._create_supplier(enterprise_type="Micro")
        pi = self._get_purchase_invoice(supplier, days=10)
        pi.submit()

        renamed = frappe.rename_doc("MSME Registration", pi.msme_registration, "UDYAM-MH-12-9999999")

        self.assertEqual(
            frappe.db.get_value("Purchase Invoice", pi.name, "msme_registration"),
            pi.msme_registration,
        )
        # the master data itself does follow the rename
        self.assertEqual(frappe.db.get_value("Supplier", supplier, "msme_registration"), renamed)

    def _get_selectable(self, posting_date):
        return {
            option["value"]: option["description"] for option in get_msme_registration_options(posting_date)
        }

    def _is_selectable(self, msme_registration, posting_date):
        return msme_registration in self._get_selectable(posting_date)

    def test_blank_udyam_number_is_reported_not_crashed_on(self):
        """before_naming runs before any mandatory check, so a blank number must
        fall through the format validation rather than blow up inside it.
        """
        self.assertRaisesRegex(
            frappe.ValidationError,
            "UDYAM Registration Number is required",
            frappe.new_doc("MSME Registration").insert,
        )

    def test_registration_is_seeded_from_the_supplier(self):
        """Through the regional party-details override, so an invoice created by
        API, import or a background job resolves it the same way the desk does.
        """
        supplier = self._create_supplier(enterprise_type="Micro")
        pi = self._get_purchase_invoice(supplier, days=10)

        self.assertEqual(
            pi.msme_registration,
            frappe.db.get_value("Supplier", supplier, "msme_registration"),
        )

    def test_nothing_is_fetched_for_a_party_without_a_supplier(self):
        """The regional override is shared with GST and runs on sales too."""
        self.assertEqual(get_msme_details({"customer": "_Test Registered Customer"}), {})

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
