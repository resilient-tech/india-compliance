# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, get_link_to_form

from india_compliance.gst_india.constants import GST_TAX_TYPES
from india_compliance.gst_india.controllers.isd_controller import ISDController
from india_compliance.gst_india.utils.isd import throw_row_table


class ISDRecipientInvoice(ISDController):
    """Branch / credit-recipient side of an ISD distribution."""

    def validate(self):
        self.setup_precision()
        self.setup_party_fields()
        self.validate_addresses()
        self.validate_turnover_and_ratio()
        self.validate_reference_distribution_invoice()
        self.validate_accounts()
        self.set_taxes_and_totals()

    def on_submit(self):
        self.make_document_gl_entries()

    def validate_reference_distribution_invoice(self):
        """When linked to an on-site ISD Distribution Invoice, reconcile against it. Skipped for pure
        manual entry (no reference)."""
        if not self.isd_distribution_invoice_reference:
            return

        reference = self.isd_distribution_invoice_reference
        ref_link = get_link_to_form("ISD Distribution Invoice", reference)

        source = frappe.db.get_value(
            "ISD Distribution Invoice",
            reference,
            ["docstatus", "distribution_gstin", "recipient_gstin", "is_credit_note"],
            as_dict=True,
        )

        if not source or source.docstatus != 1:
            frappe.throw(_("ISD Distribution Invoice {0} is not submitted.").format(ref_link))

        # the distribution GSTIN is the ISD and the recipient GSTIN the branch on both documents,
        # so the GSTINs match directly
        if source.distribution_gstin != self.distribution_gstin:
            frappe.throw(
                _("Distribution GSTIN {0} does not match ISD Distribution Invoice {1}.").format(
                    frappe.bold(self.distribution_gstin), ref_link
                )
            )

        if source.recipient_gstin != self.recipient_gstin:
            frappe.throw(
                _("Recipient GSTIN {0} does not match ISD Distribution Invoice {1}.").format(
                    frappe.bold(self.recipient_gstin), ref_link
                )
            )

        if bool(source.is_credit_note) != bool(self.is_credit_note):
            frappe.throw(
                _("Credit Note status does not match ISD Distribution Invoice {0}.").format(ref_link)
            )

        self.reconcile_distributed_amounts(reference, ref_link)

    def reconcile_distributed_amounts(self, reference, ref_link):
        """The credit received per tax head must match what the distribution invoice allotted."""
        precision = self._source_item_precision
        tolerance = 0.01

        distributed = frappe.get_all(
            "ISD Source Item",
            filters={"parent": reference, "parenttype": "ISD Distribution Invoice"},
            fields=[f"distributed_{gst_tax_type}" for gst_tax_type in GST_TAX_TYPES],
        )

        received = self.get_distributed_by_head()
        mismatched = []
        for gst_tax_type in GST_TAX_TYPES:
            expected = flt(sum(flt(row.get(f"distributed_{gst_tax_type}")) for row in distributed), precision)
            given = flt(received.get(gst_tax_type), precision)
            if abs(expected - given) > tolerance:
                mismatched.append(
                    [gst_tax_type.upper(), f"{expected:.{precision}f}", f"{given:.{precision}f}"]
                )

        if mismatched:
            throw_row_table(
                _("Distributed amounts do not match ISD Distribution Invoice {0}").format(ref_link),
                [_("Component"), _("Distributed"), _("Received")],
                mismatched,
            )
