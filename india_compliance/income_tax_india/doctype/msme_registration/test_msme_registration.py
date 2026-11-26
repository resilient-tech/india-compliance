# Copyright (c) 2026, Resilient Tech and Contributors
# See license.txt

import secrets

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase
from frappe.utils import add_days, getdate, today

from india_compliance.income_tax_india.doctype.msme_registration.msme_registration import (
    copy_latest_classification,
    copy_to_financial_year,
)
from india_compliance.income_tax_india.utils.msme import (
    get_financial_year_dates,
    get_fiscal_year_dates,
    get_indian_fiscal_year,
    get_msme_registration_details,
    get_msme_registration_status,
)

FY = "2023-2024"


def create_msme_registration(classifications=None, **kwargs):
    """MSME registration with a unique UDYAM number."""
    msme = frappe.new_doc("MSME Registration")
    kwargs.setdefault("registration_date", "2020-04-01")
    kwargs.setdefault("pan", f"AAAPL{1000 + secrets.randbelow(9000)}C")
    msme.udyam_number = kwargs.pop("udyam_number", None) or (
        f"UDYAM-MH-12-{1000000 + secrets.randbelow(9000000)}"
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

    def test_pan_is_checked_and_uppercased(self):
        self.assertEqual(create_msme_registration(pan=" aaapl1234c ").pan, "AAAPL1234C")
        self.assertRaises(frappe.ValidationError, create_msme_registration, pan="AAAPL1234")
        self.assertRaises(frappe.ValidationError, create_msme_registration, pan="")

    def test_invalid_udyam_number_rejected(self):
        self.assertRaises(frappe.ValidationError, create_msme_registration, udyam_number="INVALID-123")
        self.assertRaises(
            frappe.ValidationError, create_msme_registration, udyam_number="UDYAM-I-MH-26-0012345"
        )

    def test_valid_udyam_number_accepted_and_uppercased(self):
        msme = create_msme_registration(udyam_number="udyam-mh-12-3456789")
        self.assertEqual(msme.udyam_number, "UDYAM-MH-12-3456789")

        renamed = frappe.rename_doc("MSME Registration", msme.name, "udyam-mh-12-7654321")
        self.assertEqual(renamed, "UDYAM-MH-12-7654321")
        self.assertEqual(frappe.db.get_value("MSME Registration", renamed, "udyam_number"), renamed)

        for invalid in ("UDYAM-MH-12-12", "UDYAM-I-MH-26-0012345"):
            self.assertRaises(
                frappe.ValidationError, frappe.rename_doc, "MSME Registration", renamed, invalid
            )

    def test_activity_defaults_to_manufacturing(self):
        """Trading is the exception a user declares; Manufacturing is the norm."""
        msme = create_msme_registration(
            classifications=[{"financial_year": FY, "enterprise_type": "Micro", "activity": None}]
        )

        self.assertEqual(msme.classifications[0].activity, "Manufacturing")

    def test_invalid_financial_year_rejected(self):
        for invalid_financial_year in ("2024", "2024-2026", "24-25", "FY 2024-25"):
            self.assertRaises(
                frappe.ValidationError,
                create_msme_registration,
                classifications=[{"financial_year": invalid_financial_year, "enterprise_type": "Micro"}],
            )

    def test_duplicate_financial_year_rejected(self):
        """Two rows for one year would make the category ambiguous."""
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
        """A year ending before registration would have a period that ends before it starts."""
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
        """The period stops at the cancellation date, not the year end."""
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
        """A year starting after the cancellation cannot be classified."""
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

    def test_cancellation_keeps_suppliers_linked(self):
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
        """The Supplier stores only the link; details come from the registration."""
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

    def test_copy_checks_the_financial_year_first(self):
        self.assertRaises(frappe.ValidationError, copy_to_financial_year, [], "2025-2027")

    def test_cancelling_twice_rejected(self):
        msme = create_msme_registration(registration_date="2023-04-01")
        msme.mark_as_cancelled("2023-10-15")
        msme.reload()

        self.assertRaises(frappe.ValidationError, msme.mark_as_cancelled, "2023-11-01")

    def test_copy_to_next_year(self):
        current_year = get_indian_fiscal_year(today())
        start = int(current_year.split("-")[0])
        last_year = f"{start - 1}-{start}"
        next_year = f"{start + 1}-{start + 2}"

        to_copy = create_msme_registration(
            classifications=[
                {
                    "financial_year": f"{start - 3}-{start - 2}",
                    "enterprise_type": "Micro",
                    "activity": "Service",
                },
                {
                    "financial_year": f"{start - 2}-{start - 1}",
                    "enterprise_type": "Small",
                    "activity": "Manufacturing",
                },
            ]
        )
        already = create_msme_registration(
            classifications=[{"financial_year": current_year, "enterprise_type": "Micro"}]
        )
        later = create_msme_registration(
            classifications=[{"financial_year": next_year, "enterprise_type": "Micro"}]
        )
        cancelled = create_msme_registration(
            classifications=[{"financial_year": last_year, "enterprise_type": "Micro"}]
        )
        cancelled.mark_as_cancelled(f"{start}-01-15")
        undated = create_msme_registration(
            classifications=[{"financial_year": last_year, "enterprise_type": "Micro"}]
        )
        frappe.db.set_value("MSME Registration", undated.name, "is_cancelled", 1)
        no_rows = create_msme_registration()

        copy_to_financial_year(
            [to_copy.name, already.name, later.name, cancelled.name, no_rows.name, undated.name]
        )
        to_copy.reload()
        self.assertEqual(
            [(row.financial_year, row.enterprise_type, row.activity) for row in to_copy.classifications][-1],
            (current_year, "Small", "Manufacturing"),
        )
        for skipped in (already, later, cancelled, no_rows, undated):
            self.assertEqual(
                len(skipped.classifications),
                len(frappe.get_doc("MSME Registration", skipped.name).classifications),
            )

        copy_to_financial_year([to_copy.name])
        to_copy.reload()
        self.assertEqual([row.financial_year for row in to_copy.classifications].count(current_year), 1)

        copy_to_financial_year([to_copy.name, later.name], next_year)
        to_copy.reload()
        later.reload()
        self.assertEqual(to_copy.classifications[-1].financial_year, next_year)
        self.assertEqual(len(later.classifications), 1)

        self.assertEqual(copy_latest_classification([later.name], "next year"), [later.name])
        later.reload()
        self.assertEqual(len(later.classifications), 1)

        batch = [
            create_msme_registration(
                classifications=[{"financial_year": last_year, "enterprise_type": "Micro"}]
            ).name
            for _ in range(20)
        ]
        copy_to_financial_year(batch)
        self.assertTrue(
            all(
                frappe.db.exists(
                    "India MSME Classification", {"parent": name, "financial_year": current_year}
                )
                for name in batch
            )
        )
        self.assertRaises(frappe.ValidationError, copy_to_financial_year, [to_copy.name] * 501)

        frappe.set_user("Guest")
        try:
            self.assertRaises(frappe.PermissionError, copy_to_financial_year, [no_rows.name])
        finally:
            frappe.set_user("Administrator")


class UnitTestMSME(UnitTestCase):
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
