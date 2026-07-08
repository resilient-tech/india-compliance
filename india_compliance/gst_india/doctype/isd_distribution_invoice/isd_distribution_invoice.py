# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

from functools import reduce
from operator import add

import frappe
from frappe import _
from frappe.model.mapper import get_mapped_doc
from frappe.query_builder.functions import Coalesce, Sum
from frappe.utils import cint, flt, get_link_to_form, getdate

from india_compliance.gst_india.constants import GST_TAX_TYPES
from india_compliance.gst_india.controllers.isd_controller import ISDController
from india_compliance.gst_india.doctype.turnover_record.turnover_record import (
    upsert_turnover_record,
)
from india_compliance.gst_india.utils import validate_invoice_number
from india_compliance.gst_india.utils.isd import (
    ISD_GST_CATEGORY,
    calculate_distribution,
    sum_row_tax_by_type,
    throw_invalid_rows,
    throw_row_table,
)


class ISDDistributionInvoice(ISDController):
    _DOCTYPE_NAME = "ISD Distribution Invoice"

    def validate(self):
        # TODO: verify that validation of not allowing distribution of ineligible due to POS rules
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

    def on_submit(self):
        self.make_document_gl_entries()
        self.sync_distribution_percentage()

        frappe.enqueue(self.upsert_turnover_record, enqueue_after_commit=True)

    def on_cancel(self):
        super().on_cancel()
        self.sync_distribution_percentage(include_current=False)

    # on_cancel (reversing the GL entries) is inherited from ISDController

    def upsert_turnover_record(self):
        if not self.recipient_address:
            return

        gst_state = frappe.get_cached_value("Address", self.recipient_address, "gst_state")
        if not (self.recipient_gstin or gst_state):
            return

        upsert_turnover_record(
            gstin=self.recipient_gstin,
            gst_state=gst_state,
            amount=self.branch_turnover,
            posting_date=self.posting_date,
        )

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
        frappe.set_value(
            "Purchase Invoice",
            self.purchase_invoice,
            "isd_credit_distributed_percent",
            flt((net_distributed_itc / total_itc_available) * 100, _p),
        )

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

    def validate_distribution_limits(self):
        """The credit (and expense) distributed for a Purchase Invoice - across every ISD Distribution
        Invoice that points to it, including this one - must not exceed the credit (or expense)
        available on that Purchase Invoice (Rule 39(1)(b))."""
        if not self.purchase_invoice:
            return

        precision = self._source_item_precision
        tolerance = 0.01

        # self's totals are validated before this
        available_itc = flt(sum(sum_row_tax_by_type(row, "total") for row in self.source_items), precision)
        available_expense = flt(sum(flt(row.total_expense) for row in self.source_items), precision)

        already = self.get_distributed_for_purchase_invoice()

        current_itc = flt(
            sum(sum_row_tax_by_type(row, "distributed") for row in self.source_items), precision
        )
        current_expense = flt(sum(flt(row.distributed_expense) for row in self.source_items), precision)

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
                        "Over-distribution: distributing {0} amount {1} for Purchase Invoice {2}"
                        " against available ({3})."
                    ).format(
                        label,
                        frappe.bold(f"{total - available:.{precision}f}"),
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
        order_by="is_primary_address DESC",
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

    distribution_address = _guess_address(source.get("distribution_gstin"), extra_filters=filters)
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
    recipient_address = _guess_address(source.recipient_gstin, extra_filters=filters)

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
            "distribution_address": distribution_address,
            "recipient_address": recipient_address,
            "cost_center": default_cost_center,
            "project": None,
            "isd_provisional_account": default_isd_provisional_account,
        }
    )

    for row in recipient.source_items:
        row.update(
            {
                "expense_head": default_expense_account,
                "cost_center": default_cost_center,
                "project": None,
            }
        )


def set_missing_values(source, target):
    """Postprocess for the ISD Distribution -> ISD Recipient mapping"""
    target.isd_distribution_invoice_reference = source.name
    target.posting_date = source.posting_date
    target.set("taxes", [])

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
def create_isd_recipient_invoice(source_name: str, submit_on_creation: bool | None = None):
    """creating a isd recipient invoice from a isd distrubiion invocie"""
    # submit on creation -> None, assume open_mapped_doc called it
    frappe.has_permission("ISD Distribution Invoice", "read", throw=True)
    frappe.has_permission("ISD Recipient Invoice", "write", throw=True)

    if frappe.db.exists(
        "ISD Recipient Invoice", {"isd_distribution_invoice_reference": source_name, "docstatus": ["<", 2]}
    ):
        frappe.throw(
            _("ISD Recipient Invoice already exists for ISD Distribution Invoice {0}").format(
                get_link_to_form("ISD Distribution Invoice", source_name)
            )
        )

    recipient = get_mapped_doc(
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

    # when using open_mapped_doc must return the draft document without running validations
    if submit_on_creation is not None:
        recipient.insert(ignore_permissions=True)

        if cint(submit_on_creation):
            recipient.submit()
            status = _("created and submitted")
        else:
            status = _("saved as a draft")

        frappe.msgprint(
            _("ISD Recipient Invoice {0} {1}.").format(
                get_link_to_form("ISD Recipient Invoice", recipient.name), status
            ),
            alert=True,
            indicator="green",
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
