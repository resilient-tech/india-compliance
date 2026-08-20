# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

from functools import reduce
from operator import add

import frappe
from frappe import _
from frappe.model.mapper import get_mapped_doc
from frappe.query_builder.functions import Coalesce, Sum
from frappe.utils import flt, get_link_to_form, getdate

from india_compliance.gst_india.constants import GST_TAX_TYPES, ISD_GST_CATEGORY
from india_compliance.gst_india.utils import validate_invoice_number
from india_compliance.gst_india.utils.isd import (
    calculate_distribution,
    distribute_expense_with_isd_credit,
    get_purchase_doc,
    sum_row_tax_by_type,
    throw_invalid_rows,
    throw_row_table,
)
from india_compliance.gst_india.utils.isd_controller import ISDController


class ISDDistributionInvoice(ISDController):
    _DOCTYPE_NAME = "ISD Distribution Invoice"

    def validate(self):
        self.setup_precision()
        self.setup_party_fields()
        validate_invoice_number(self)
        self.validate_addresses()
        self.validate_turnover_and_ratio()
        self.validate_purchase_invoice()
        self.validate_total_turnover()
        self.validate_source_items()
        calculate_distribution(self)  # override js calculations
        self.validate_accounts()
        self.set_taxes_and_totals()
        self.clamp_to_distribution_limits()

    def on_submit(self):
        self.make_gl_entries()
        self.sync_distribution_percentage()

        gstin, gst_state = frappe.get_cached_value("Address", self.party_address, ["gstin", "gst_state"])
        turnover_record_data = [(gstin, gst_state, self.branch_turnover, self.posting_date)]

        frappe.enqueue(
            "india_compliance.gst_india.utils.isd._upsert_turnover_records",
            data=turnover_record_data,
            enqueue_after_commit=True,
        )

        if not self.is_against_party and frappe.db.get_single_value(
            "GST Settings", "auto_create_isd_recipient_invoice"
        ):
            _create_isd_recipient_invoice(self.name)

    # on_cancel (reversing the GL entries) is inherited from ISDController
    def on_cancel(self):
        super().on_cancel()
        self.sync_distribution_percentage(include_current=False)

    def sync_distribution_percentage(self, include_current=True):
        already = self.get_distributed_for_purchase_invoice()

        current_invoice_distributed_itc = sum(
            sum_row_tax_by_type(row, "distributed") for row in self.source_items
        )
        total_itc_available = sum(sum_row_tax_by_type(row, "total") for row in self.source_items)

        net_distributed_itc = already.itc
        if include_current:
            net_distributed_itc += current_invoice_distributed_itc

        _p = frappe.get_precision("Purchase Invoice", "isd_credit_distributed_percent")

        # edge case of 99.9999% distribution rounded to misleading 100% distribution
        distribution_percentage = (
            flt((net_distributed_itc / total_itc_available) * 100, _p) if total_itc_available else 100.0
        )
        if distribution_percentage == flt(100, _p) and (net_distributed_itc != total_itc_available):
            distribution_percentage = flt(100 - 10**-_p, _p)

        if distribution_percentage > 100:
            frappe.throw(
                _("Distributed ITC ({0}%) exceeds the available ITC on Purchase Invoice {1}.").format(
                    distribution_percentage, get_link_to_form("Purchase Invoice", self.purchase_invoice)
                )
            )

        frappe.db.set_value(
            "Purchase Invoice",
            self.purchase_invoice,
            "isd_credit_distributed_percent",
            distribution_percentage,
        )

    def validate_purchase_invoice(self):
        pi = get_purchase_doc(self.purchase_invoice)
        pi_link = get_link_to_form("Purchase Invoice", self.purchase_invoice)

        # Posting Date should be on or after the Purchase Invoice (GSTR-6 Rule 39)
        if getdate(pi.posting_date) > getdate(self.posting_date):
            frappe.throw(
                _("Posting date of Purchase Invoice {0} is after this ISD Distribution Invoice.").format(
                    pi_link
                )
            )

        if pi.company != self.company:
            frappe.throw(_("Purchase Invoice {0} belongs to a different company.").format(pi_link))

        if pi.company_gstin != frappe.get_cached_value("Address", self.company_address, "gstin"):
            frappe.throw(
                _("Purchase Invoice {0} is booked under a different Distribution GSTIN.").format(pi_link)
            )

    def validate_total_turnover(self):
        precision = self.precision("total_turnover")
        distributed_total = frappe.db.get_value(
            "ISD Distribution Invoice",
            {"purchase_invoice": self.purchase_invoice, "docstatus": 1, "name": ("!=", self.name)},
            "total_turnover",
        )
        if not distributed_total or flt(distributed_total, precision) == flt(self.total_turnover, precision):
            return

        frappe.throw(
            _("Total Turnover must be {0}, as used by the earlier distributions of {1}.").format(
                frappe.bold(flt(distributed_total, precision)),
                get_link_to_form("Purchase Invoice", self.purchase_invoice),
            ),
            title=_("Total Turnover Changed"),
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

        for row in self.source_items:
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

    # ------------------------------------------------------------------ distribution limits
    def clamp_to_distribution_limits(self):
        # TODO: should this at least be logged in the error log?
        # otherwise we don't have any trace of clamping
        if not self.source_items:
            return

        itc_surplus, expense_surplus = self.get_distribution_surplus()
        if itc_surplus:
            self.clamp_itc_surplus(itc_surplus)
        if expense_surplus:
            self.clamp_expense_surplus(expense_surplus)

        if itc_surplus or expense_surplus:
            self.set_tax_totals()
            self.isd_provisional_amount = flt(
                self.total_eligible + self.total_ineligible + self.total_expense, self._tax_precision
            )
            self._notify_adjustment(itc_surplus + expense_surplus)

    def get_distribution_surplus(self):
        current_itc = sum(sum_row_tax_by_type(row, "distributed") for row in self.source_items)
        current_expense = sum(flt(row.distributed_expense) for row in self.source_items)
        already = self.get_distributed_for_purchase_invoice()

        if self.is_credit_note and self.credit_note_against:
            against_values = frappe.get_value(
                "ISD Distribution Invoice",
                self.credit_note_against,
                ["total_eligible", "total_ineligible", "total_expense"],
                as_dict=True,
            )
            # credit allowed to reverse is minimum of credit_note_against's distributed and total available for distribution
            allowed_itc = min(
                flt(
                    against_values.total_eligible + against_values.total_ineligible,
                    self._source_item_precision,
                ),
                flt(already.itc, self._source_item_precision),
            )
            allowed_expense = min(
                flt(against_values.total_expense, self._source_item_precision),
                flt(already.expense, self._source_item_precision),
            )
            return (
                min(0.0, flt(allowed_itc + current_itc, self._source_item_precision)),
                min(0.0, flt(allowed_expense + current_expense, self._source_item_precision)),
            )

        available_itc = sum(sum_row_tax_by_type(row, "total") for row in self.source_items)
        available_expense = sum(flt(row.total_expense) for row in self.source_items)

        return (
            max(0.0, flt(already.itc + current_itc - available_itc, self._source_item_precision)),
            max(
                0.0,
                flt(already.expense + current_expense - available_expense, self._source_item_precision),
            ),
        )

    def clamp_itc_surplus(self, surplus):
        row = self.source_items[0]

        # source item carries the converted heads (IGST inter-state, CGST/SGST intra-state)
        if flt(row.distributed_cgst) or flt(row.distributed_sgst):
            row.distributed_cgst = flt(flt(row.distributed_cgst) - surplus / 2, self._source_item_precision)
            row.distributed_sgst = flt(flt(row.distributed_sgst) - surplus / 2, self._source_item_precision)
        else:
            row.distributed_igst = flt(flt(row.distributed_igst) - surplus, self._source_item_precision)

        # taxes table carries the source heads being reduced
        cgst_tax = next((t for t in self.taxes if t.gst_tax_type == "cgst"), None)
        sgst_tax = next((t for t in self.taxes if t.gst_tax_type == "sgst"), None)
        if cgst_tax or sgst_tax:
            cgst_tax.tax_amount = flt(flt(cgst_tax.tax_amount) - surplus / 2, self._tax_precision)
            sgst_tax.tax_amount = flt(flt(sgst_tax.tax_amount) - surplus / 2, self._tax_precision)
            # also clamp the cache set_tax_totals() re-reads tax_amount from, else the next
            # set_tax_totals() call (below) discards this clamp and restores the unclamped amount
            self._tax_amounts_by_head["cgst"] = cgst_tax.tax_amount
            self._tax_amounts_by_head["sgst"] = sgst_tax.tax_amount
        else:
            igst_tax = next((t for t in self.taxes if t.gst_tax_type == "igst"), None)
            igst_tax.tax_amount = flt(flt(igst_tax.tax_amount) - surplus, self._tax_precision)
            self._tax_amounts_by_head["igst"] = igst_tax.tax_amount

    def clamp_expense_surplus(self, surplus):
        row = self.source_items[0]
        row.distributed_expense = flt(flt(row.distributed_expense) - surplus, self._source_item_precision)

    def _notify_adjustment(self, surplus):
        frappe.msgprint(
            _("{0} was {1} for Purchase Invoice {2}. It has been adjusted on row #1.").format(
                frappe.bold(f"{abs(surplus):.{self._source_item_precision}f}"),
                _("over-distributed") if surplus > 0 else _("over-reversed"),
                get_link_to_form("Purchase Invoice", self.purchase_invoice),
            ),
            title=_("Distribution Adjusted"),
            indicator="blue",
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
        return frappe._dict(
            itc=row.get("itc"),
            expense=row.get("expense"),
        )


def _guess_address(gstin, extra_filters=None):
    "guess address internal function for creating inter company invoices"
    if not gstin:
        return None

    filters = [
        ["disabled", "=", 0],
        ["gstin", "=", gstin],
    ]
    if extra_filters:
        filters.extend(extra_filters)

    names = frappe.get_list(
        "Address",
        filters=filters,
        pluck="name",
        order_by="is_primary_address DESC, name",
        limit=1,
    )
    return names[0] if names else None


def apply_against_party_overrides(source, recipient):
    recipient_company = frappe.db.get_value(source.party_type, source.party, "represents_company")
    if not recipient_company:
        frappe.throw(
            _(
                "{0} {1} does not represent a company, so an inter-company ISD Recipient"
                " Invoice cannot be created."
            ).format(source.party_type, frappe.bold(source.party))
        )

    party_type = party = None
    filters = [
        ["gst_category", "=", ISD_GST_CATEGORY],
        ["Dynamic Link", "link_doctype", "!=", "Company"],
    ]

    distribution_address = _guess_address(source.get("company_gstin"), extra_filters=filters)
    if distribution_address:
        link = frappe.db.get_value(
            "Dynamic Link",
            {
                "parent": distribution_address,
                "parenttype": "Address",
                "link_doctype": ["!=", "Company"],
            },
            ["link_doctype", "link_name"],
            as_dict=True,
        )
        if link:
            party_type, party = link.link_doctype, link.link_name

    filters = [
        ["gst_category", "!=", ISD_GST_CATEGORY],
        ["Dynamic Link", "link_doctype", "=", "Company"],
        ["Dynamic Link", "link_name", "=", recipient_company],
    ]
    recipient_address = _guess_address(source.get("party_gstin"), extra_filters=filters)

    # Accounts and accounting dimensions belong to the source company; re-default them for the new
    # (recipient) company instead.
    default_cost_center, default_expense_account, default_isd_provisional_account = frappe.get_cached_value(
        "Company",
        recipient_company,
        ["cost_center", "default_expense_account", "default_isd_provisional_account"],
    )

    recipient.update(
        {
            "company": recipient_company,
            "is_against_party": 1,
            "party_type": party_type,
            "party": party,
            "party_address": distribution_address,
            "company_address": recipient_address,
            "cost_center": default_cost_center,
            "project": None,
            "isd_provisional_account": default_isd_provisional_account,
        }
    )

    for row in recipient.source_items:
        row.update(
            {
                "expense_head": default_expense_account if distribute_expense_with_isd_credit() else None,
                "cost_center": default_cost_center,
                "project": None,
            }
        )


def set_missing_values(source, target):
    """Postprocess for the ISD Distribution -> ISD Recipient mapping"""
    target.isd_distribution_invoice_reference = source.name
    target.posting_date = source.posting_date
    target.set("taxes", [])
    target.company_address = source.party_address
    target.party_address = source.company_address

    if source.is_credit_note and source.credit_note_against:
        target.credit_note_against = frappe.db.get_value(
            "ISD Recipient Invoice",
            {
                "isd_distribution_invoice_reference": source.credit_note_against,
                "is_credit_note": 0,
                "docstatus": 1,
            },
        )

    if source.is_against_party:
        apply_against_party_overrides(source, target)


@frappe.whitelist()
def create_isd_recipient_invoice(source_name: str):
    frappe.has_permission("ISD Distribution Invoice", "read", doc=source_name, throw=True)
    frappe.has_permission("ISD Recipient Invoice", "create", throw=True)

    return _map_isd_recipient_invoice(source_name)


def _map_isd_recipient_invoice(source_name: str):
    if frappe.db.exists(
        "ISD Recipient Invoice", {"isd_distribution_invoice_reference": source_name, "docstatus": ["<", 2]}
    ):
        frappe.throw(
            _("ISD Recipient Invoice already exists for ISD Distribution Invoice {0}").format(
                get_link_to_form("ISD Distribution Invoice", source_name)
            )
        )

    doc = get_mapped_doc(
        "ISD Distribution Invoice",
        source_name,
        {
            "ISD Distribution Invoice": {
                "doctype": "ISD Recipient Invoice",
                "field_no_map": [
                    "naming_series",
                    "amended_from",
                    "purchase_invoice",
                    "credit_note_against",
                ],
                "validation": {"docstatus": ["=", 1]},
            },
            "ISD Source Item": {
                "doctype": "ISD Source Item",
                "field_no_map": ["purchase_invoice_item"],
            },
        },
        postprocess=set_missing_values,
    )

    return doc


def _create_isd_recipient_invoice(source_name: str):
    recipient = _map_isd_recipient_invoice(source_name)
    recipient.insert()
    recipient.submit()

    frappe.msgprint(
        _("ISD Recipient Invoice {0} created").format(
            get_link_to_form("ISD Recipient Invoice", recipient.name)
        ),
        alert=True,
    )

    return recipient


@frappe.whitelist()
def create_credit_note(source_name: str):
    frappe.has_permission("ISD Distribution Invoice", "read", doc=source_name, throw=True)
    frappe.has_permission("ISD Distribution Invoice", "create", throw=True)

    def set_missing_values(source, target):
        target.is_credit_note = 1
        target.credit_note_against = source.name

    return get_mapped_doc(
        "ISD Distribution Invoice",
        source_name,
        {
            "ISD Distribution Invoice": {
                "doctype": "ISD Distribution Invoice",
                "field_no_map": ["naming_series", "amended_from"],
                "validation": {"docstatus": ["=", 1], "is_credit_note": ["=", 0]},
            },
            "ISD Source Item": {
                "doctype": "ISD Source Item",
            },
        },
        postprocess=set_missing_values,
    )
