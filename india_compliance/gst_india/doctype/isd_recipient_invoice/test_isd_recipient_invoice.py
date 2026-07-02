# Copyright (c) 2026, Resilient Tech and Contributors
# See license.txt

from frappe.tests import IntegrationTestCase

from india_compliance.gst_india.constants import GST_TAX_TYPES
from india_compliance.gst_india.doctype.isd_distribution_invoice.test_isd_distribution_invoice import (
    RECIPIENT_KA_GSTIN,
    VALIDATION_ERROR,
    build_distribution,
    make_isd_pi,
    make_recipient_invoice,
    make_source_item,
    setup_isd_fixtures,
    submit_distribution,
    teardown_isd_fixtures,
)

# The recipient shares the distribution invoice's link chain (ISD Source Item -> Purchase Invoice
# Item -> Item Tax Template ...); those records already exist, so keep them out of dependency loading.
EXTRA_TEST_RECORD_DEPENDENCIES = []
IGNORE_TEST_RECORD_DEPENDENCIES = [
    "Address",
    "Purchase Invoice",
    "Purchase Invoice Item",
    "Cost Center",
    "Tax Category",
    "Item",
    "UOM",
    "Item Tax Template",
    "Project",
    "Company",
    "Account",
    "ISD Distribution Invoice",
    "ISD Recipient Invoice",
    "ISD Source Item",
    "ISD Tax Item",
]


class IntegrationTestISDRecipientInvoice(IntegrationTestCase):
    """Basic validations for ISD Recipient Invoice (excludes bulk generation and GL entries)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        setup_isd_fixtures(cls)

    @classmethod
    def tearDownClass(cls):
        teardown_isd_fixtures()
        super().tearDownClass()

    def _recipient(self, **overrides):
        fields = dict(
            distribution_address=self.isd_address.name,
            recipient_address=self.recipient_address.name,
            branch_turnover=25,
            total_turnover=100,
        )
        source_items = overrides.pop("source_items", None)
        fields.update(overrides)
        return make_recipient_invoice(source_items=source_items, **fields)

    def _submit_reference(self, branch=25, total=100):
        """A submitted ISD Distribution Invoice, on its own Purchase Invoice, to reconcile against."""
        pi = make_isd_pi(self.isd_address.name)
        return submit_distribution(
            pi, self.isd_address.name, self.recipient_address.name, branch=branch, total=total
        )

    # ------------------------------------------------------------------ addresses / ISD party
    def test_address_validations(self):
        # On the recipient side the company owns the recipient address; one linked to a Customer
        # (not the company) is invalid.
        doc = self._recipient(recipient_address="_Test Registered Customer-Billing")
        self.assertRaisesRegex(
            VALIDATION_ERROR, "is not valid for this ISD distribution", doc.validate_address_links
        )

        # Against a party, the counterparty (distribution) address must be linked to the party.
        doc = self._recipient(
            recipient_address=self.recipient_address.name,
            distribution_address=self.isd_address.name,
            is_against_party=1,
            party_type="Customer",
            party=self.branch_customer.name,
        )
        self.assertRaisesRegex(
            VALIDATION_ERROR, "is not valid for this ISD distribution", doc.validate_address_links
        )

        # The distribution address must be of ISD category; the recipient address must not be.
        doc = self._recipient(distribution_address=self.recipient_address.name)
        self.assertRaisesRegex(
            VALIDATION_ERROR, "not registered as an Input Service Distributor", doc.validate_isd_party
        )

        doc = self._recipient(recipient_address=self.isd_address.name)
        self.assertRaisesRegex(
            VALIDATION_ERROR, "must not be an Input Service Distributor", doc.validate_isd_party
        )

        # A fully valid pair passes and the place of supply is derived from each address.
        doc = self._recipient()
        doc.validate_addresses()
        self.assertEqual(doc.distribution_pos, "24-Gujarat")
        self.assertEqual(doc.recipient_pos, "24-Gujarat")

    # ------------------------------------------------------------------ inter-state IGST-only
    def test_gst_account_type_validations(self):
        # inter-state: CGST/SGST cannot be received; only IGST is valid
        doc = self._recipient(
            recipient_address=self.recipient_address_ka.name,
            source_items=[{"item_code": "_Test Service Item", "distributed_cgst": 100}],
        )
        doc.setup_precision()
        self.assertRaisesRegex(
            VALIDATION_ERROR, "must be distributed as IGST", doc.validate_gst_account_types
        )

        # inter-state with only IGST passes
        doc = self._recipient(
            recipient_address=self.recipient_address_ka.name,
            source_items=[{"item_code": "_Test Service Item", "distributed_igst": 200}],
        )
        doc.setup_precision()
        doc.validate_gst_account_types()

        # intra-state CGST/SGST is allowed
        doc = self._recipient(
            source_items=[
                {"item_code": "_Test Service Item", "distributed_cgst": 100, "distributed_sgst": 100}
            ],
        )
        doc.setup_precision()
        doc.validate_gst_account_types()

    # ------------------------------------------------------------------ reference reconciliation
    def test_reference_mismatch_rejected(self):
        ref = self._submit_reference()

        # the referenced distribution invoice must be submitted
        pi = make_isd_pi(self.isd_address.name)
        draft = build_distribution(pi, self.isd_address.name, self.recipient_address.name)
        draft.insert()
        doc = self._recipient(isd_distribution_invoice_reference=draft.name)
        self.assertRaisesRegex(
            VALIDATION_ERROR, "is not submitted", doc.validate_reference_distribution_invoice
        )

        # the distribution GSTIN must match the reference
        doc = self._recipient(isd_distribution_invoice_reference=ref.name)
        doc.distribution_gstin = RECIPIENT_KA_GSTIN
        self.assertRaisesRegex(
            VALIDATION_ERROR,
            "Distribution GSTIN .* does not match",
            doc.validate_reference_distribution_invoice,
        )

        # the recipient GSTIN must match the reference
        doc = self._recipient(isd_distribution_invoice_reference=ref.name)
        doc.recipient_gstin = RECIPIENT_KA_GSTIN
        self.assertRaisesRegex(
            VALIDATION_ERROR, "Recipient GSTIN .* does not match", doc.validate_reference_distribution_invoice
        )

        # the credit note status must match the reference
        doc = self._recipient(isd_distribution_invoice_reference=ref.name, is_credit_note=1)
        self.assertRaisesRegex(
            VALIDATION_ERROR, "Credit Note status does not match", doc.validate_reference_distribution_invoice
        )

        # the distributed amounts per tax head must match the reference
        doc = self._recipient(
            isd_distribution_invoice_reference=ref.name,
            source_items=[{"item_code": "_Test Service Item", "distributed_cgst": 999999}],
        )
        doc.setup_precision()
        with self.assertRaises(VALIDATION_ERROR) as cm:
            doc.validate_reference_distribution_invoice()
        self.assertIn("CGST", str(cm.exception))

    def test_reference_reconciliation_passes(self):
        # no reference -> the reconciliation is skipped
        doc = self._recipient(source_items=[{"item_code": "_Test Service Item", "distributed_igst": 100}])
        self.assertIsNone(doc.isd_distribution_invoice_reference)
        doc.validate_reference_distribution_invoice()

        # amounts that mirror the reference exactly reconcile cleanly
        ref = self._submit_reference(branch=25, total=100)
        source_items = [
            {f"distributed_{tax}": row.get(f"distributed_{tax}") for tax in GST_TAX_TYPES}
            for row in ref.source_items
        ]
        doc = self._recipient(isd_distribution_invoice_reference=ref.name, source_items=source_items)
        doc.setup_precision()
        doc.validate_reference_distribution_invoice()

    # ------------------------------------------------------------------ smoke: full manual validate
    def test_recipient_validate_passes_for_manual_entry(self):
        doc = self._recipient(source_items=make_source_item(self.pi, ratio=0.25))
        doc.insert()
        self.assertEqual(doc.docstatus, 0)
        self.assertTrue(doc.get("taxes"))
