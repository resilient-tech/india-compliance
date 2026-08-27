# Copyright (c) 2026, Resilient Tech and Contributors
# See license.txt

import random

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase
from frappe.utils import add_days, getdate, today

from india_compliance.income_tax_india.utils.msme import (
    get_financial_year_dates,
    get_financial_years_between,
    get_fiscal_year_dates,
    get_indian_fiscal_year,
    get_msme_registration_details,
    get_msme_registration_status,
    update_msme_classification,
)

FY = "2023-2024"


def create_msme_registration(classifications=None, **kwargs):
    """MSME registration with a unique UDYAM number."""
    msme = frappe.new_doc("MSME Registration")
    kwargs.setdefault("registration_date", "2020-04-01")
    msme.udyam_number = kwargs.pop("udyam_number", None) or (
        f"UDYAM-MH-12-{random.randint(1000000, 9999999)}"
    )
    msme.update(kwargs)

    for classification in classifications or []:
        msme.append("classifications", classification)

    msme.insert()
    return msme


def create_supplier(msme_registration=None):
    supplier = frappe.new_doc("Supplier")
    supplier.supplier_name = frappe.generate_hash("MSME Registration", 10)
    supplier.supplier_group = frappe.db.get_value("Supplier Group", {"is_group": 0})
    supplier.msme_registration = msme_registration
    supplier.insert()
    return supplier.name


class IntegrationTestMSME(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        frappe.db.savepoint("before_test_msme")

    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback(save_point="before_test_msme")

    def test_invalid_udyam_number_rejected(self):
        self.assertRaises(frappe.ValidationError, create_msme_registration, udyam_number="INVALID-123")

    def test_valid_udyam_number_accepted_and_uppercased(self):
        msme = create_msme_registration(udyam_number="udyam-mh-12-3456789")
        self.assertEqual(msme.udyam_number, "UDYAM-MH-12-3456789")

    def test_activity_defaults_to_manufacturing(self):
        """Trading is the exception a user declares; Manufacturing is the norm."""
        msme = create_msme_registration(
            classifications=[{"financial_year": FY, "enterprise_type": "Micro", "activity": None}]
        )

        self.assertEqual(msme.classifications[0].activity, "Manufacturing")
        self.assertTrue(get_msme_registration_details(msme.name, "2023-06-01").is_43b_applicable)

    def test_invalid_financial_year_rejected(self):
        for invalid_financial_year in ("2024", "2024-2026", "24-25", "FY 2024-25"):
            self.assertRaises(
                frappe.ValidationError,
                create_msme_registration,
                classifications=[{"financial_year": invalid_financial_year, "enterprise_type": "Micro"}],
            )

    def test_duplicate_financial_year_rejected(self):
        """A period is always the year it names, so two rows for one year would
        make the classification ambiguous.
        """
        self.assertRaisesRegex(
            frappe.ValidationError,
            "Duplicate MSME classification",
            create_msme_registration,
            classifications=[
                {"financial_year": "2024-2025", "enterprise_type": enterprise_type}
                for enterprise_type in ("Micro", "Small")
            ],
        )

    def test_year_ending_before_the_registration_is_rejected(self):
        """Classifying a year the enterprise was not yet registered for would
        leave a period starting after it ends.
        """
        self.assertRaisesRegex(
            frappe.ValidationError,
            "Not registered in Financial Year",
            create_msme_registration,
            registration_date="2025-06-01",
            classifications=[{"financial_year": "2023-2024", "enterprise_type": "Micro"}],
        )

    def test_cancellation_before_registration_rejected(self):
        msme = create_msme_registration(registration_date="2023-04-01")
        self.assertRaises(frappe.ValidationError, msme.mark_as_cancelled, "2023-03-01")

    def test_cancelled_registration_is_not_msme(self):
        msme = create_msme_registration(
            registration_date="2023-04-01",
            classifications=[{"financial_year": FY, "enterprise_type": "Micro"}],
        )
        msme.mark_as_cancelled("2023-10-15")

        # supplies accepted before cancellation are still covered
        self.assertEqual(get_msme_registration_details(msme.name, "2023-10-15").enterprise_type, "Micro")
        self.assertFalse(get_msme_registration_details(msme.name, "2023-10-16").valid)

    def test_cancellation_shortens_the_period_of_that_year(self):
        """The stored period must say what the registration actually covered,
        not the whole year it was cancelled in.
        """
        msme = create_msme_registration(
            registration_date="2023-04-01",
            classifications=[{"financial_year": FY, "enterprise_type": "Micro"}],
        )

        msme.mark_as_cancelled("2023-10-15")
        msme.reload()
        self.assertEqual(getdate(msme.classifications[0].to_date), getdate("2023-10-15"))

        msme.undo_cancellation()
        msme.reload()
        self.assertEqual(getdate(msme.classifications[0].to_date), getdate("2024-03-31"))

    def test_year_starting_after_the_cancellation_is_rejected(self):
        """The mirror of the registration rule: a year the enterprise was no
        longer registered for cannot be classified.
        """
        msme = create_msme_registration(
            registration_date="2023-04-01",
            classifications=[
                {"financial_year": FY, "enterprise_type": "Micro"},
                {"financial_year": "2024-2025", "enterprise_type": "Micro"},
            ],
        )

        self.assertRaisesRegex(
            frappe.ValidationError,
            "Not registered in Financial Year",
            msme.mark_as_cancelled,
            "2023-10-15",
        )

    def test_cancellation_can_be_undone(self):
        """A mistyped cancellation date must be fixable without touching the DB."""
        msme = create_msme_registration(
            registration_date="2023-04-01",
            classifications=[{"financial_year": FY, "enterprise_type": "Micro"}],
        )
        msme.mark_as_cancelled("2023-10-15")
        self.assertFalse(get_msme_registration_details(msme.name, "2023-10-16").valid)

        msme.undo_cancellation()

        self.assertEqual(get_msme_registration_details(msme.name, "2023-10-16").enterprise_type, "Micro")
        self.assertRaises(frappe.ValidationError, msme.undo_cancellation)

    def test_cancellation_unlinks_suppliers_on_request(self):
        msme = create_msme_registration(registration_date="2023-04-01")
        suppliers = [create_supplier(msme.name) for _ in range(2)]

        self.assertCountEqual(msme.get_linked_suppliers(), suppliers)

        msme.mark_as_cancelled("2023-10-15", unlink_suppliers=True)

        for supplier in suppliers:
            self.assertIsNone(frappe.db.get_value("Supplier", supplier, "msme_registration"))

    def test_unlinking_is_logged_on_the_supplier(self):
        """A bulk update leaves no version, so the unlink is recorded as a comment."""
        msme = create_msme_registration(registration_date="2023-04-01")
        supplier = create_supplier(msme.name)

        msme.mark_as_cancelled("2023-10-15", unlink_suppliers=True)

        comments = frappe.get_all(
            "Comment",
            filters={"reference_doctype": "Supplier", "reference_name": supplier},
            pluck="content",
        )

        self.assertTrue(
            any(msme.name in comment for comment in comments),
            "unlinking the registration was not recorded on the supplier",
        )

    def test_cancellation_keeps_suppliers_linked_by_default(self):
        msme = create_msme_registration(registration_date="2023-04-01")
        supplier = create_supplier(msme.name)

        msme.mark_as_cancelled("2023-10-15")

        self.assertEqual(frappe.db.get_value("Supplier", supplier, "msme_registration"), msme.name)

    def test_cancelled_without_date_is_never_msme(self):
        """is_cancelled is the flag; a missing date must not read as active."""
        msme = create_msme_registration(classifications=[{"financial_year": FY, "enterprise_type": "Micro"}])
        frappe.db.set_value("MSME Registration", msme.name, "is_cancelled", 1, update_modified=False)

        self.assertFalse(get_msme_registration_details(msme.name, "2023-05-01").valid)

    def test_supplier_details_are_read_on_demand(self):
        """Nothing is copied onto the Supplier, so the details cannot drift from
        the master - the form fetches them when it shows them.
        """
        msme = create_msme_registration(
            classifications=[
                {
                    "financial_year": get_indian_fiscal_year(today()),
                    "enterprise_type": "Micro",
                    "activity": "Manufacturing",
                }
            ]
        )
        supplier = create_supplier(msme.name)
        status = get_msme_registration_status(frappe.db.get_value("Supplier", supplier, "msme_registration"))

        self.assertEqual(status.enterprise_type, "Micro")
        self.assertEqual(status.activity, "Manufacturing")
        self.assertTrue(status.valid)
        self.assertFalse(frappe.db.has_column("Supplier", "msme_enterprise_type"))

    def test_annual_bump_carries_classification_forward(self):
        current_financial_year = get_indian_fiscal_year(today())
        previous_year = int(current_financial_year.split("-")[0]) - 1

        msme = create_msme_registration(
            classifications=[
                {
                    "financial_year": f"{previous_year}-{previous_year + 1}",
                    "enterprise_type": "Micro",
                    "activity": "Trading",
                }
            ]
        )

        update_msme_classification()
        carried = get_msme_registration_details(msme.name)
        self.assertEqual(carried.enterprise_type, "Micro")
        self.assertEqual(carried.activity, "Trading")

        # never overwrites a year that is already classified
        update_msme_classification()
        self.assertEqual(
            frappe.db.count(
                "India MSME Classification", {"parenttype": "MSME Registration", "parent": msme.name}
            ),
            2,
        )

    def test_annual_bump_skips_cancelled_registration(self):
        """A cancelled registration covers no new supplies, so its classification
        must not be carried into the new FY.
        """
        previous_year = int(get_indian_fiscal_year(today()).split("-")[0]) - 1

        msme = create_msme_registration(
            classifications=[
                {"financial_year": f"{previous_year}-{previous_year + 1}", "enterprise_type": "Micro"}
            ]
        )
        msme.mark_as_cancelled(today())

        update_msme_classification()
        self.assertEqual(
            frappe.db.count(
                "India MSME Classification", {"parenttype": "MSME Registration", "parent": msme.name}
            ),
            1,
        )

    def test_annual_bump_fills_every_year_it_missed(self):
        """A run missed for years would otherwise leave the registration
        unclassified, and an unclassified registration is invisible to the reports.
        """
        start_year = int(get_indian_fiscal_year(today()).split("-")[0]) - 3

        msme = create_msme_registration(
            classifications=[{"financial_year": f"{start_year}-{start_year + 1}", "enterprise_type": "Micro"}]
        )

        update_msme_classification()

        self.assertEqual(get_msme_registration_details(msme.name).enterprise_type, "Micro")

    def test_carried_row_is_resolvable_by_date(self):
        """The bump uses bulk_insert, which bypasses the document hooks. A row
        with no period is invisible to every lookup, so it must set one itself.
        """
        previous_year = int(get_indian_fiscal_year(today()).split("-")[0]) - 1

        msme = create_msme_registration(
            classifications=[
                {
                    "financial_year": f"{previous_year}-{previous_year + 1}",
                    "enterprise_type": "Micro",
                }
            ]
        )
        update_msme_classification()

        from_date, to_date = get_fiscal_year_dates()
        carried = frappe.db.get_value(
            "India MSME Classification",
            {"parent": msme.name, "financial_year": get_indian_fiscal_year(today())},
            ["from_date", "to_date"],
            as_dict=True,
        )

        self.assertEqual(getdate(carried.from_date), from_date)
        self.assertEqual(getdate(carried.to_date), to_date)

    def test_classification_period_is_derived_on_save(self):
        """A row is resolved by date, so saving one must always give it a period."""
        msme = create_msme_registration(classifications=[{"financial_year": FY, "enterprise_type": "Micro"}])
        row = msme.classifications[0]

        self.assertEqual(getdate(row.from_date), getdate("2023-04-01"))
        self.assertEqual(getdate(row.to_date), getdate("2024-03-31"))
        self.assertEqual(get_msme_registration_details(msme.name, "2023-06-01").enterprise_type, "Micro")

    def test_period_starts_at_a_mid_year_registration_date(self):
        """An enterprise registered in November was not an MSE the previous April."""
        msme = create_msme_registration(
            registration_date="2023-11-01",
            classifications=[{"financial_year": FY, "enterprise_type": "Micro"}],
        )
        row = msme.classifications[0]

        self.assertEqual(getdate(row.from_date), getdate("2023-11-01"))
        self.assertEqual(getdate(row.to_date), getdate("2024-03-31"))
        self.assertFalse(get_msme_registration_details(msme.name, "2023-06-01").valid)
        self.assertEqual(get_msme_registration_details(msme.name, "2023-11-01").enterprise_type, "Micro")

    def test_future_cancellation_date_rejected(self):
        msme = create_msme_registration(registration_date="2023-04-01")
        self.assertRaises(frappe.ValidationError, msme.mark_as_cancelled, add_days(today(), 1))

    def test_cancelling_twice_rejected(self):
        msme = create_msme_registration(registration_date="2023-04-01")
        msme.mark_as_cancelled("2023-10-15")
        msme.reload()

        self.assertRaises(frappe.ValidationError, msme.mark_as_cancelled, "2023-11-01")


class UnitTestMSME(UnitTestCase):
    """Pure date/applicability logic - no database, so UnitTestCase (faster)."""

    def test_indian_fiscal_year_boundaries(self):
        # March belongs to the FY that started the previous April.
        self.assertEqual(get_indian_fiscal_year("2025-03-31"), "2024-2025")
        # April starts a new FY.
        self.assertEqual(get_indian_fiscal_year("2025-04-01"), "2025-2026")
        self.assertEqual(get_indian_fiscal_year("2024-12-15"), "2024-2025")
        self.assertEqual(get_indian_fiscal_year("2024-01-01"), "2023-2024")

    def test_fiscal_year_dates(self):
        self.assertEqual(get_fiscal_year_dates("2024-12-15"), (getdate("2024-04-01"), getdate("2025-03-31")))
        self.assertEqual(
            get_financial_year_dates("2024-2025"), (getdate("2024-04-01"), getdate("2025-03-31"))
        )

    def test_financial_years_between(self):
        self.assertEqual(get_financial_years_between("2023-06-01", "2025-02-01"), ["2023-2024", "2024-2025"])
        self.assertEqual(get_financial_years_between("2024-05-01", "2024-06-01"), ["2024-2025"])
        # a range straddling 31 March spans two FYs
        self.assertEqual(get_financial_years_between("2024-03-31", "2024-04-01"), ["2023-2024", "2024-2025"])
