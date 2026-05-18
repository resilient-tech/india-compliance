# Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from erpnext.accounts.utils import get_fiscal_year
from erpnext.controllers.accounts_controller import AccountsController
from frappe import _
from frappe.model.document import Document
from frappe.model.mapper import get_mapped_doc
from frappe.query_builder.functions import Coalesce, Sum
from frappe.utils import flt, today
from pypika.terms import Case, Tuple

from india_compliance.gst_india.doctype.turnover_record.turnover_record import upsert_turnover_record
from india_compliance.gst_india.utils import get_gst_accounts_by_type, get_place_of_supply


class ISDInvoice(Document):
    get_gl_dict = AccountsController.get_gl_dict
    get_value_in_transaction_currency = AccountsController.get_value_in_transaction_currency
    get_voucher_subtype = AccountsController.get_voucher_subtype
    company_currency = AccountsController.company_currency

    def validate(self):
        # TODO: validations remaining to be verified
        self.clear_fields_when_is_against_party_not_set()
        self.set_pos_from_gstin()
        self.validate_isd_party() #
        self.validate_pan_consistency() #
        self.validate_distribution_limits()
        self.validate_inter_company_transaction() #
        self.autoset_taxes() #

    def autoset_taxes(self):
        """Populate taxes child table and totals from distributed source invoice amounts."""
        source_invoices = self.source_invoices or []
        if not source_invoices:
            self.taxes = []
            return

        total_igst = sum(flt(r.distributed_igst) for r in source_invoices)
        total_cgst = sum(flt(r.distributed_cgst) for r in source_invoices)
        total_sgst = sum(flt(r.distributed_sgst) for r in source_invoices)
        total_cess = sum(flt(r.distributed_cess) for r in source_invoices)
        total_cess_non_advol = sum(flt(r.distributed_cess_non_advol) for r in source_invoices)

        accounts = get_gst_accounts_by_type(self.company, "Input", throw=False) or {}

        tax_type_map = [
            ("igst", accounts.get("igst_account"), total_igst),
            ("cgst", accounts.get("cgst_account"), total_cgst),
            ("sgst", accounts.get("sgst_account"), total_sgst),
            ("cess", accounts.get("cess_account"), total_cess),
            ("cess_non_advol", accounts.get("cess_non_advol_account"), total_cess_non_advol),
        ]

        self.taxes = []
        for gst_tax_type, account_head, tax_amount in tax_type_map:
            if (not account_head):
                continue
            if not tax_amount:
                continue
            self.append("taxes", {
                "account_head": account_head,
                "gst_tax_type": gst_tax_type,
                "tax_amount": tax_amount,
            })

        self.total_eligible = sum(
            flt(r.distributed_igst) + flt(r.distributed_cgst) + flt(r.distributed_sgst) + flt(r.distributed_cess)
            for r in source_invoices
            if not r.is_ineligible_for_itc
        )
        self.total_ineligible = sum(
            flt(r.distributed_igst) + flt(r.distributed_cgst) + flt(r.distributed_sgst) + flt(r.distributed_cess)
            for r in source_invoices
            if r.is_ineligible_for_itc
        )

    def set_pos_from_gstin(self):
        """Set place of supply fields from company/party GSTIN."""
        for gstin_field, pos_field in (
            ("company_gstin", "company_pos"),
            ("party_gstin", "party_pos"),
        ):
            gstin = self.get(gstin_field)
            self.set(
                pos_field,
                get_place_of_supply(frappe._dict(company_gstin=gstin), "Purchase Invoice")
                if gstin
                else None,
            )

    def clear_fields_when_is_against_party_not_set(self):
        """Clear fields that depend on is_against_party when it is not set."""
        if self.is_against_party:
            return

        for field in ("party_type", "party", "credit_flow", "party_account"):
            if self.get(field):
                self.set(field, None)

    def validate_pan_consistency(self):
        """Ensure company GSTIN and party GSTIN share the same PAN."""
        if not self.party_gstin or not self.company_gstin:
            return
        company_pan = self.company_gstin[2:12]
        party_pan = self.party_gstin[2:12]

        if company_pan != party_pan:
            frappe.throw(
                _(
                    "PAN of Company GSTIN {0} and Party GSTIN {1} must be the same."
                ).format(frappe.bold(self.company_gstin),frappe.bold(self.party_gstin),)
            )

    def validate_isd_party(self):
        """Ensure at least one party is registered as an Input Service Distributor."""
        addresses = [self.company_address, self.party_address]

        gst_categories = frappe.db.get_list(
            "Address",
            filters={"name": ("in", addresses), "gst_category": "Input Service Distributor"},
            pluck="gst_category",
        )

        if not gst_categories:
            frappe.throw(_("At least one party must be registered as an Input Service Distributor (ISD)."))

    def validate_distribution_limits(self):
        """Validate that distributed amounts do not exceed available amounts per purchase invoice."""
        # self.is_credit_note is excluded — credit notes reduce distributed totals via signed()
        # in other documents' already_distributed queries; they don't need their own limit check.
        if self.is_credit_note or not self.source_invoices:
            return

        # Key: (purchase_invoice, is_ineligible_for_itc)
        purchase_invoices = list(
            {(row.purchase_invoice, row.is_ineligible_for_itc) for row in self.source_invoices}
        )

        isd_source_item = frappe.qb.DocType("ISD Invoice Source Item")
        isd_invoice = frappe.qb.DocType("ISD Invoice")

        tax_fields = ("igst", "cgst", "sgst", "cess", "cess_non_advol")

        def signed(field):
            """Negate distributed amounts from credit notes so they reduce the running total."""
            return Case().when(isd_invoice.is_credit_note == 1, -field).else_(field)

        def total_distributed(item):
            return sum(signed(getattr(item, f"distributed_{field}")) for field in tax_fields)

        def sum_tax(row, prefix):
            return sum(flt(getattr(row, f"{prefix}_{field}")) for field in tax_fields)

        # Sum of all tax distributed against each (purchase_invoice, is_ineligible_for_itc) key
        # across other submitted ISD invoices that were created at or before this one.
        already_distributed = {
            (row.purchase_invoice, row.is_ineligible_for_itc): flt(row.total_distributed)
            for row in (
                frappe.qb.from_(isd_source_item)
                .join(isd_invoice)
                .on(isd_source_item.parent == isd_invoice.name)
                .select(
                    isd_source_item.purchase_invoice,
                    isd_source_item.is_ineligible_for_itc,
                    Sum(total_distributed(isd_source_item)).as_("total_distributed"),
                )
                .where(
                    Tuple(isd_source_item.purchase_invoice, isd_source_item.is_ineligible_for_itc)
                    .isin(purchase_invoices)
                )
                .where(isd_invoice.docstatus == 1)
                .where(isd_invoice.name != (self.name or ""))
                .where(isd_invoice.creation <= self.creation)
                .groupby(isd_source_item.purchase_invoice, isd_source_item.is_ineligible_for_itc)
                .run(as_dict=True)
            )
        }

        # Build both dicts in a single pass over source_invoices.
        # available_* fields hold the total tax claimable from each purchase invoice.
        # distributed_* fields hold what this document is distributing.
        available_amounts: dict = {}
        current_distributed: dict = {}

        for row in self.source_invoices:
            key = (row.purchase_invoice, row.is_ineligible_for_itc)
            available_amounts[key] = available_amounts.get(key, 0) + sum_tax(row, "total")
            current_distributed[key] = current_distributed.get(key, 0) + sum_tax(row, "distributed")

        for key, distributed in current_distributed.items():
            available = available_amounts.get(key, 0) - already_distributed.get(key, 0)
            if distributed > available:
                purchase_invoice, is_ineligible = key
                label = "ineligible" if is_ineligible else "eligible"
                frappe.throw(
                    _(
                        "For purchase invoice {0}, {1} tax available is {2}"
                        " but you are trying to distribute {3}."
                    ).format(
                        frappe.bold(purchase_invoice),
                        label,
                        flt(available),
                        flt(distributed),
                    )
                )

    def validate_inter_company_transaction(self):
        if not self.is_against_party or not self.party:
            return

        internal = "is_internal_supplier" if self.party_type == "Supplier" else "is_internal_customer"

        if frappe.db.get_value(self.party_type, {"name": self.party, internal: 1}, "name") != self.party:
            return

        allowed_companies = frappe.get_all(
            "Allowed To Transact With",
            filters={"parenttype": self.party_type, "parent": self.party},
            pluck="company",
        )
        if self.company not in allowed_companies:
            frappe.throw(
                _(
                    "{0} {1} is not allowed to transact with Company {2}. Add the company in"
                    " 'Allowed To Transact With' section of the {0} record."
                ).format(self.party_type, self.party, self.company)
            )

    @frappe.whitelist()
    def get_purchase_invoices(self, purchase_invoices: list, distribution_ratio: float = 0.0):
        """Get purchase invoices with eligible/ineligible taxes for source invoices table

        purchase_invoices -- list of purchase invoice IDs
        distribution_ratio -- distribution ratio to be applied
        Action: fetches source invoices and fills the source invoices table in ISD Invoice
        """

        if not purchase_invoices:
            frappe.msgprint(_("No Purchase Invoices selected"))
            return []

        frappe.has_permission("Purchase Invoice", "read", throw=True)
        frappe.has_permission("ISD Invoice", "write", throw=True)

        # Remove empty rows (rows with no purchase_invoice set)
        self.source_invoices = [row for row in self.get("source_invoices") if row.purchase_invoice]

        existing_items = [
            (item.purchase_invoice, item.is_ineligible_for_itc) for item in self.source_invoices
        ]
        items_to_add = get_source_invoices_from_purchase_invoices(purchase_invoices)

        for item in items_to_add:
            if (item.purchase_invoice, item.is_ineligible_for_itc) not in existing_items:
                self.append("source_invoices", {**item, "distribution_ratio": distribution_ratio})


@frappe.whitelist()
def get_source_invoices_from_purchase_invoices(purchase_invoices: list | str):
# TODO: ensure only service items 
    if isinstance(purchase_invoices, str):
        purchase_invoices = frappe.parse_json(purchase_invoices)

    pi = frappe.qb.DocType("Purchase Invoice")
    pi_item = frappe.qb.DocType("Purchase Invoice Item")

    result = (
        frappe.qb.from_(pi_item)
        .join(pi)
        .on(pi_item.parent == pi.name)
        .select(
            pi_item.parent.as_("purchase_invoice"),
            pi_item.is_ineligible_for_itc,
            Sum(pi_item.igst_amount).as_("total_igst"),
            Sum(pi_item.cgst_amount).as_("total_cgst"),
            Sum(pi_item.sgst_amount).as_("total_sgst"),
            Sum(pi_item.cess_amount).as_("total_cess"),
            Sum(pi_item.cess_non_advol_amount).as_("total_cess_non_advol"),
        )
        .where(pi_item.parent.isin(purchase_invoices))
        .where(pi.docstatus == 1)
        .groupby(pi_item.parent, pi_item.is_ineligible_for_itc)
        .having(
            (Sum(pi_item.igst_amount) > 0)
            | (Sum(pi_item.cgst_amount) > 0)
            | (Sum(pi_item.sgst_amount) > 0)
            | (Sum(pi_item.cess_amount) > 0)
            | (Sum(pi_item.cess_non_advol_amount) > 0)
        )
        .run(as_dict=True)
    )

    return result


@frappe.whitelist()
def get_input_gst_accounts(company: str):
    return get_gst_accounts_by_type(company, "Input", throw=False)


# TODO: incomplete, js side needs to be implemented, search on change of text
@frappe.whitelist()
def search_purchase_invoice(txt: str, company: str, billing_address: str | None = None):
    frappe.has_permission("Purchase Invoice", "read", throw=True)

    filters = [
        ["docstatus", "=", 1],
        ["company", "=", company],
        ["name", "like", f"%{txt}%"],
    ]
    if billing_address:
        filters.append(["billing_address", "=", billing_address])

    return frappe.get_list(
        "Purchase Invoice",
        filters=filters,
        pluck="name",
        limit=20,
    )

@frappe.whitelist()
def create_inter_company_invoice(source_name: str, target_doc:str|None=None):

    def post_process(source, target):
        new_direction = "Inward" if source.credit_flow == "Outward" else "Outward"
        new_party_type = "Customer" if new_direction == "Outward" else "Supplier"

        new_company = frappe.get_value(source.party_type, source.party, "represents_company")
        if not new_company:
            frappe.throw(
                _("{0} {1} does not represent a Company.").format(source.party_type, source.party)
            )

        internal_field = "is_internal_customer" if new_party_type == "Customer" else "is_internal_supplier"
        new_party_name = frappe.get_value(
            new_party_type,
            {"represents_company": source.company, internal_field: 1},
            "name",
        )
        if not new_party_name:
            frappe.throw(_("No {0} found representing {1}.").format(new_party_type, source.company))

        target.is_against_party = 1
        target.credit_flow = new_direction
        target.party_type = new_party_type
        target.company = new_company
        target.party = new_party_name
        target.inter_company_invoice_reference = source.name
        target.party_address = source.company_address
        target.party_gstin = source.company_gstin
        target.party_pos = source.company_pos
        target.party_address_display = source.party_address_display
        # TODO: this does not trigger autosetting the gstin and display fields
        # trigger js for party_address
        target.company_address = ""
        # TODO: set the company address by searching based on the gstin of source.company_address


    return get_mapped_doc(
        "ISD Invoice",
        source_name,
        {
            "ISD Invoice": {
                "doctype": "ISD Invoice",
                "validation": {"docstatus": ["=", 1]},
                "field_map": {
                    "naming_series": "naming_series",
                    "is_credit_note": "is_credit_note",
                    "posting_date": "posting_date",
                    "distribution_ratio": "distribution_ratio",
                    "credit_note_against": "credit_note_against",
                },
            },
            "ISD Invoice Source Item": {
                "doctype": "ISD Invoice Source Item",
                "field_map": [
                    "purchase_invoice",
                    "is_ineligible_for_itc",
                    "distribution_ratio",
                    "total_igst",
                    "total_cgst",
                    "total_sgst",
                    "total_cess",
                    "total_cess_non_advol",
                ],
            },
        },
        target_doc,
        post_process,
    )


@frappe.whitelist()
def get_distribution_heads(party_type: str, party: str, posting_date: str, address: str | None = None):
    fiscal_year = get_fiscal_year(posting_date, company=party, raise_on_missing=False) or get_fiscal_year(today(), company=party, raise_on_missing=False)
    fiscal_year = fiscal_year[0] if fiscal_year else None

    Address = frappe.qb.DocType("Address")
    DynamicLink = frappe.qb.DocType("Dynamic Link")
    TurnoverRecord = frappe.qb.DocType("Turnover Record")

    query = (
        frappe.qb.from_(Address)
        .join(DynamicLink)
        .on(DynamicLink.parent == Address.name)
        .left_join(TurnoverRecord)
        .on(
            (TurnoverRecord.gstin == Address.gstin)
            & (TurnoverRecord.gst_state == Address.gst_state)
            & (TurnoverRecord.fiscal_year == fiscal_year)
        )
        .select(
            Address.name,
            Address.gstin,
            Address.gst_state,
            Address.gst_category,
            Coalesce(TurnoverRecord.amount, 0).as_("turnover_amount"),
        )
        .where(
            (DynamicLink.link_doctype == party_type)
            & (DynamicLink.link_name == party)
            & (Address.gst_category != "Input Service Distributor")
        )
    )

    if address:
        query = query.where(Address.name == address)

    return query.run(as_dict=True)


def make_isd_invoice(
    source_name: str,
    target_doc: str | None = None,
    distribution_ratio: float = 0.0,
    party_address: str | None = None,
    party_type: str | None = None,
    party: str | None = None,
):
    """
    Insert a new ISD Invoice based on a Purchase Invoice
    Permission checked in get_mapped_doc, validation ignored while inserting
    """

    def set_missing_values(source, target):
        target.distribution_ratio = flt(distribution_ratio)
        target.party_address = party_address

        if party_type and party:
            target.is_against_party = 1
            target.party_type = party_type
            target.party = party

        result = get_source_invoices_from_purchase_invoices([source_name])
        if not result:
            frappe.throw(
                _("Purchase Invoice {0} has no taxable amount to distribute.").format(
                    frappe.bold(source_name)
                )
            )

        for row in result:
            target.append("source_invoices", {**row, "distribution_ratio": flt(distribution_ratio)})

        _calculate_distribution(target)

    doc = get_mapped_doc(
        "Purchase Invoice",
        source_name,
        {
            "Purchase Invoice": {
                "doctype": "ISD Invoice",
                "field_map": {
                    "company": "company",
                    "billing_address": "company_address",
                },
                "field_no_map": ["naming_series", "party_address"],
                "validation": {
                    "docstatus": ["=", 1],
                    "is_isd_applicable": ["=", 1],
                },
            },
        },
        target_doc,
        postprocess=set_missing_values,
    )

    doc.flags.ignore_validate = True
    doc.insert(ignore_permissions=True)

    is_invalid_insertion = False

    try:
        doc.flags.ignore_validate = False
        doc.save()
    except frappe.ValidationError:
        frappe.clear_messages()
        is_invalid_insertion = True
    return doc, is_invalid_insertion


@frappe.whitelist()
def bulk_create_isd_invoices(rows: list | str, source_name: str):
    if isinstance(rows, str):
        rows = frappe.parse_json(rows)

    invoices = []
    invalid_invoices = []
    for row in rows:
        amount = row.get("amount") or 0
        if not amount:
            continue

        fiscal_year = row.get("fiscal_year")
        if not fiscal_year:
            purchase_invoice = frappe.get_doc("Purchase Invoice", source_name)
            fiscal_year = purchase_invoice.fiscal_year or get_fiscal_year(purchase_invoice.posting_date, company=purchase_invoice.company)[0]

        upsert_turnover_record(row["gstin"], row["gst_category"], row["gst_state"], fiscal_year, amount)

        isd_doc, is_invalid_insertion = make_isd_invoice(
            source_name=source_name,
            target_doc=None,
            distribution_ratio=row.get("distribution_ratio", 0),
            party_address=row["party_address"],
            party_type=row["party_type"],
            party=row["party"],
        )
        invoices.append(isd_doc.name)
        if is_invalid_insertion:
            invalid_invoices.append(isd_doc.name)

    return invoices, invalid_invoices


def _calculate_distribution(doc):
    """Calculate distributed tax amounts for each source invoice row."""
    IMPORT_GST_CATEGORIES = ("Overseas", "SEZ")

    company_state = (
        frappe.db.get_value("Address", doc.company_address, "gst_state")
        if doc.company_address
        else None
    )
    party_state = (
        frappe.db.get_value("Address", doc.party_address, "gst_state")
        if doc.party_address
        else None
    )
    party_gst_category = (
        frappe.db.get_value("Address", doc.party_address, "gst_category")
        if doc.party_address
        else None
    )

    is_inter_state = (company_state != party_state) or (party_gst_category in IMPORT_GST_CATEGORIES)

    for row in doc.source_invoices:
        ratio = flt(row.distribution_ratio) / 100

        if is_inter_state:
            row.distributed_igst = (
                flt(row.total_igst) + flt(row.total_cgst) + flt(row.total_sgst)
            ) * ratio
            row.distributed_cgst = 0
            row.distributed_sgst = 0
        else:
            row.distributed_igst = flt(row.total_igst) * ratio
            row.distributed_cgst = flt(row.total_cgst) * ratio
            row.distributed_sgst = flt(row.total_sgst) * ratio

        row.distributed_cess = flt(row.total_cess) * ratio
        row.distributed_cess_non_advol = flt(row.total_cess_non_advol) * ratio


