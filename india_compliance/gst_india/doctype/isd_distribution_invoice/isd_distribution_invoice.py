# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

from functools import reduce
from operator import add

import frappe
from frappe import _
from frappe.query_builder.functions import Coalesce, Sum
from frappe.utils import flt, get_link_to_form, getdate

from india_compliance.gst_india.constants import GST_TAX_TYPES
from india_compliance.gst_india.controllers.isd_controller import ISDController
from india_compliance.gst_india.utils import validate_invoice_number
from india_compliance.gst_india.utils.isd import (
    calculate_distribution,
    sum_row_tax_by_type,
    throw_invalid_rows,
    throw_row_table,
)


class ISDDistributionInvoice(ISDController):
    _DOCTYPE_NAME = "ISD Distribution Invoice"

    def validate(self):
        self.setup_precision()
        self.setup_party_fields()
        validate_invoice_number(self)
        self.validate_addresses()
        self.validate_turnover_and_ratio()
        self.validate_purchase_invoice()
        self.validate_source_items()
        calculate_distribution(self)  # override js calculations
        self.validate_distribution_limits()
        self.validate_accounts()
        self.set_taxes_and_totals()

    def validate_purchase_invoice(self):
        if not self.purchase_invoice:
            frappe.throw(_("Purchase Invoice is required."))

        pi = frappe.db.get_value(
            "Purchase Invoice",
            self.purchase_invoice,
            ["docstatus", "is_isd_applicable", "posting_date", "company", "company_gstin"],
            as_dict=True,
        )

        pi_link = get_link_to_form("Purchase Invoice", self.purchase_invoice)

        if not pi or pi.docstatus != 1:
            frappe.throw(_("Purchase Invoice {0} is not submitted.").format(pi_link))

        if not pi.is_isd_applicable:
            frappe.throw(_("Purchase Invoice {0} is not ISD applicable.").format(pi_link))

        # Posting Date should be on or after the Purchase Invoice (GSTR-6 Rule 39)
        if getdate(pi.posting_date) > getdate(self.posting_date):
            frappe.throw(
                _("Posting date of Purchase Invoice {0} is after this ISD Distribution Invoice.").format(
                    pi_link
                )
            )

        if pi.company != self.company:
            frappe.throw(_("Purchase Invoice {0} belongs to a different company.").format(pi_link))

        if pi.company_gstin != self.distribution_gstin:
            frappe.throw(
                _("Purchase Invoice {0} is booked under a different Distribution GSTIN.").format(pi_link)
            )

    def validate_source_items(self):
        """One to One mapping of purchase invoice items and source items"""
        # validate_purchase_invoice (runs first) guarantees self.purchase_invoice is set
        pi_items = {
            item.name: item
            for item in frappe.get_all(
                "Purchase Invoice Item",
                filters={"parent": self.purchase_invoice},
                fields=[
                    "name",
                    "idx",
                    *[f"{gst_tax_type}_amount" for gst_tax_type in GST_TAX_TYPES],
                    "base_net_amount",
                ],
            )
        }

        precision = self._source_item_precision
        invalid_links = []
        invalid_totals = []
        duplicate_rows = []
        seen = set()

        for row in self.source_invoices:
            pi_item = pi_items.get(row.purchase_invoice_item)
            if not pi_item:
                # row points to an item not on this Purchase Invoice
                invalid_links.append([row.idx, row.item_code or row.purchase_invoice_item])
                continue

            if row.purchase_invoice_item in seen:
                duplicate_rows.append([row.idx, row.item_code or row.purchase_invoice_item])
                continue
            seen.add(row.purchase_invoice_item)

            # validate totals
            for gst_tax_type in GST_TAX_TYPES:
                if (expected := flt(pi_item.get(f"{gst_tax_type}_amount"), precision)) != (
                    given := flt(row.get(f"total_{gst_tax_type}"), precision)
                ):
                    invalid_totals.append([str(row.idx), gst_tax_type.upper(), expected, given])

            if (expected := flt(pi_item.base_net_amount, precision)) != (
                given := flt(row.total_expense, precision)
            ):
                invalid_totals.append([str(row.idx), _("Expense"), expected, given])

        if invalid_links:
            throw_invalid_rows(
                _("Following source items do not belong to Purchase Invoice {0}").format(
                    frappe.bold(self.purchase_invoice)
                ),
                invalid_links,
            )

        if duplicate_rows:
            throw_invalid_rows(
                _("Following items of Purchase Invoice {0} are added more than once").format(
                    frappe.bold(self.purchase_invoice)
                ),
                duplicate_rows,
            )

        # every Purchase Invoice Item must be present
        missing_rows = [[pi_item.idx, name] for name, pi_item in pi_items.items() if name not in seen]
        if missing_rows:
            throw_invalid_rows(
                _("Following items of Purchase Invoice {0} are missing from the source items").format(
                    frappe.bold(self.purchase_invoice)
                ),
                sorted(missing_rows),
            )

        if invalid_totals:
            throw_row_table(
                _("Source item taxes do not match the Purchase Invoice"),
                [_("Row"), _("Component"), _("Purchase Invoice"), _("Entered")],
                invalid_totals,
            )

    def validate_distribution_limits(self):
        """The credit (and expense) distributed for a Purchase Invoice - across every ISD Distribution
        Invoice that points to it, including this one - must not exceed the credit (or expense)
        available on that Purchase Invoice (Rule 39(1)(b))."""
        if not self.purchase_invoice:
            return

        precision = self._source_item_precision
        tolerance = 0.1

        # self's totals are validated before this
        available_itc = flt(sum(sum_row_tax_by_type(row, "total") for row in self.source_invoices), precision)
        available_expense = flt(sum(flt(row.total_expense) for row in self.source_invoices), precision)

        already = self.get_distributed_for_purchase_invoice()

        current_itc = flt(
            sum(sum_row_tax_by_type(row, "distributed") for row in self.source_invoices), precision
        )
        current_expense = flt(sum(flt(row.distributed_expense) for row in self.source_invoices), precision)

        total_itc = flt(already.itc + current_itc, precision)
        total_expense = flt(already.expense + current_expense, precision)

        for label, total, available in (
            (_("ITC"), total_itc, available_itc),
            (_("expense"), total_expense, available_expense),
        ):
            # distribution can't over-distribute
            if total > available + tolerance:
                frappe.throw(
                    _(
                        "Over-distribution: the total {0} distributed ({1}) for Purchase Invoice {2}"
                        " exceeds the {0} available ({3})."
                    ).format(
                        label,
                        frappe.bold(f"{total:.{precision}f}"),
                        get_link_to_form("Purchase Invoice", self.purchase_invoice),
                        frappe.bold(f"{available:.{precision}f}"),
                    ),
                    title=_("Over Distribution"),
                )
            # credit notes can't reverse more than was distributed (net can't drop below zero)
            if total < -tolerance:
                frappe.throw(
                    _(
                        "Over-reversal: the {0} reversed exceeds the {0} distributed for Purchase"
                        " Invoice {1} (net distributed {2})."
                    ).format(
                        label,
                        get_link_to_form("Purchase Invoice", self.purchase_invoice),
                        frappe.bold(f"{total:.{precision}f}"),
                    ),
                    title=_("Over Reversal"),
                )

    def get_distributed_for_purchase_invoice(self):
        """Sum of distributed ITC and expense on every other submitted ISD Distribution Invoice
        that distributes self.purchase_invoice (excludes this document)."""
        isd_source_item = frappe.qb.DocType("ISD Source Item")
        isd_invoice = frappe.qb.DocType("ISD Distribution Invoice")

        distributed_itc = reduce(
            add,
            (
                Coalesce(getattr(isd_source_item, f"distributed_{gst_tax_type}"), 0)
                for gst_tax_type in GST_TAX_TYPES
            ),
        )
        result = (
            frappe.qb.from_(isd_source_item)
            .join(isd_invoice)
            .on(isd_source_item.parent == isd_invoice.name)
            .where(isd_invoice.purchase_invoice == self.purchase_invoice)
            .where(isd_invoice.docstatus == 1)
            .where(isd_invoice.name != (self.name or ""))
            .select(
                Coalesce(Sum(distributed_itc), 0).as_("itc"),
                Coalesce(Sum(isd_source_item.distributed_expense), 0).as_("expense"),
            )
            .run(as_dict=True)
        )
        row = result[0] if result else {}
        precision = self._source_item_precision
        return frappe._dict(
            itc=flt(row.get("itc"), precision),
            expense=flt(row.get("expense"), precision),
        )
