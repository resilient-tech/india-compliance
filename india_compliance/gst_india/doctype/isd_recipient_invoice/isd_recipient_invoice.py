# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, get_link_to_form

from india_compliance.gst_india.constants import GST_TAX_TYPES
from india_compliance.gst_india.utils.isd import throw_row_table
from india_compliance.gst_india.utils.isd_controller import ISDController
from india_compliance.gst_india.utils.itc_claim import (
    _is_gstr3b_filed,
    set_or_validate_itc_claim_period,
    validate_itc_claim_period_on_update_after_submit,
)


class ISDRecipientInvoice(ISDController):
    """Branch / credit-recipient side of an ISD distribution."""

    def onload(self):
        if self.docstatus != 1:
            return

        if self.itc_claim_period:
            self.set_onload(
                "is_itc_period_filed",
                _is_gstr3b_filed(self.company_gstin, self.itc_claim_period),
            )

    def validate(self):
        self.setup_precision()
        self.setup_party_fields()
        self.validate_addresses()
        self.validate_credit_note_direction()
        self.validate_credit_note_against()
        self.validate_reference_distribution_invoice()
        self.validate_external_isd_invoice_number()
        self.validate_accounts()
        self.set_taxes_and_totals()

        set_or_validate_itc_claim_period(self)
        if self.docstatus == 0:
            self.reconciliation_status = "Unreconciled"

    def before_update_after_submit(self):
        validate_itc_claim_period_on_update_after_submit(self)

    def on_submit(self):
        self.make_gl_entries()

    # on_trash (deleting the GL entries) is inherited from ISDController
    def on_cancel(self):
        super().on_cancel()

        # a cancelled invoice must not keep holding on to its 2A/2B match
        frappe.db.set_value(
            "GST Inward Supply",
            {"link_doctype": self.doctype, "link_name": self.name},
            {
                "match_status": "",
                "link_name": "",
                "link_doctype": "",
                "action": "No Action",
            },
        )

    def validate_credit_note_direction(self):
        for gst_tax_type in (*GST_TAX_TYPES, "expense"):
            fieldname = f"distributed_{gst_tax_type}"
            amount = sum(flt(row.get(fieldname)) for row in self.source_items)
            label = fieldname.replace("_", " ").title()

            if self.is_credit_note and amount > 0:
                frappe.throw(_("{0} must be negative in credit note").format(label))

            if not self.is_credit_note and amount < 0:
                frappe.throw(_("{0} must be positive in distribution document").format(label))

    def validate_credit_note_against(self):
        if not self.credit_note_against:
            return

        if not self.is_credit_note:
            frappe.throw(_("Only a credit note can be issued against another distribution."))

        if self.credit_note_against == self.name:
            frappe.throw(_("A credit note cannot be issued against itself."))

        against = frappe.db.get_value(
            "ISD Recipient Invoice",
            self.credit_note_against,
            ["docstatus", "is_credit_note", "party_gstin", "company_gstin"],
            as_dict=True,
        )
        against_link = get_link_to_form("ISD Recipient Invoice", self.credit_note_against)

        if not against or against.docstatus != 1:
            frappe.throw(_("ISD Recipient Invoice {0} is not submitted.").format(against_link))

        if against.is_credit_note:
            frappe.throw(_("ISD Recipient Invoice {0} is itself a credit note.").format(against_link))

        if (against.company_gstin, against.party_gstin) != (self.company_gstin, self.party_gstin):
            frappe.throw(
                _("ISD Recipient Invoice {0} is between a different pair of GSTINs.").format(against_link)
            )

    def validate_external_isd_invoice_number(self):
        """The number the distributing ISD gave this document. mandatory_depends_on only binds the
        form, so validate it here -- reconciliation matches 2A/2B on this number, and an invoice
        without one can never match."""
        if self.isd_distribution_invoice_reference:
            return

        if not self.external_isd_invoice_number:
            frappe.throw(_("ISD Invoice Number is required when no ISD Distribution Invoice is linked."))

        duplicate = frappe.db.exists(
            "ISD Recipient Invoice",
            {
                "party_gstin": self.party_gstin,
                "external_isd_invoice_number": self.external_isd_invoice_number,
                "is_credit_note": self.is_credit_note,
                "docstatus": ("!=", 2),
                "name": ("!=", self.name),
            },
        )
        if duplicate:
            frappe.throw(
                _("ISD Invoice Number {0} has already been entered in {1}.").format(
                    frappe.bold(self.external_isd_invoice_number),
                    get_link_to_form("ISD Recipient Invoice", duplicate),
                )
            )

    def validate_reference_distribution_invoice(self):
        """When linked to an on-site ISD Distribution Invoice, reconcile against it. Skipped for pure
        manual entry (no reference)."""
        if not self.isd_distribution_invoice_reference:
            return

        reference = self.isd_distribution_invoice_reference
        ref_link = get_link_to_form("ISD Distribution Invoice", reference)

        duplicate_check = frappe.db.exists(
            "ISD Recipient Invoice",
            {
                "isd_distribution_invoice_reference": reference,
                "name": ("!=", self.name),
                "docstatus": 1,
            },
        )

        if duplicate_check:
            frappe.throw(
                _(
                    "ISD Distribution Invoice {0} is already linked to another submitted ISD Recipient Invoice."
                ).format(ref_link)
            )

        source = frappe.db.get_value(
            "ISD Distribution Invoice",
            reference,
            ["docstatus", "company_gstin", "party_gstin", "is_credit_note"],
            as_dict=True,
        )

        if not source or source.docstatus != 1:
            frappe.throw(_("ISD Distribution Invoice {0} is not submitted.").format(ref_link))

        # NOTE: the reference is the other side of the same distribution, so company/party INVERT:
        # its company_gstin is the ISD (our party_gstin) and its party_gstin is the branch
        # (our company_gstin). Do not "simplify" these to same-named comparisons.
        if source.company_gstin != self.party_gstin:
            frappe.throw(
                _("Distribution GSTIN {0} does not match ISD Distribution Invoice {1}.").format(
                    frappe.bold(self.party_gstin), ref_link
                )
            )

        if source.party_gstin != self.company_gstin:
            frappe.throw(
                _("Recipient GSTIN {0} does not match ISD Distribution Invoice {1}.").format(
                    frappe.bold(self.company_gstin), ref_link
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
