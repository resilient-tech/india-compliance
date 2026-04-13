# Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from erpnext.accounts.general_ledger import make_gl_entries, make_reverse_gl_entries
from erpnext.controllers.accounts_controller import AccountsController
from frappe import _
from frappe.contacts.doctype.address.address import get_address_display
from frappe.model.document import Document
from frappe.query_builder.functions import Sum

from india_compliance.gst_india.utils import get_gst_accounts_by_type


class ISDInvoice(Document):
    get_gl_dict = AccountsController.get_gl_dict
    get_value_in_transaction_currency = AccountsController.get_value_in_transaction_currency
    get_voucher_subtype = AccountsController.get_voucher_subtype
    company_currency = AccountsController.company_currency

    def validate(self):
        self.set_address_display()
        #TODO: validations
        # duplication based on (purchase_invoice, is_ineligible_for_itc)

    def set_address_display(self):
        address_dict = {
            "company_address": "company_address_display",
            "party_address": "party_address_display",
        }
        for address_field, display_field in address_dict.items():
            if self.get(address_field):
                self.set(display_field, get_address_display(self.get(address_field)))

    @frappe.whitelist()
    def calculate_distribution(self):
        default_distribution_ratio = self.distribution_ratio or 0
        company_state = self.company_state
        party_state = self.party_state
        # assuming all invoices are billied to either company state or party state

        for row in self.get("source_items") or []:
            ratio = (row.distribution_ratio or default_distribution_ratio) / 100
            is_inter_state = company_state != party_state

            if is_inter_state:
                row.distributed_igst = (row.total_cgst + row.total_sgst + row.total_igst) * ratio
                row.distributed_cgst = 0
                row.distributed_sgst = 0
            else:
                row.distributed_igst = row.total_igst * ratio
                row.distributed_cgst = row.total_cgst * ratio
                row.distributed_sgst = row.total_sgst * ratio

            row.distributed_cess = row.total_cess * ratio
            row.distributed_cess_non_advol = row.total_cess_non_advol * ratio

    @frappe.whitelist()
    def calculate_taxes_and_totals(self):
        source_items = self.get("source_items") or []
        if not source_items:
            return

        total_igst = sum(row.distributed_igst for row in source_items)
        total_cgst = sum(row.distributed_cgst for row in source_items)
        total_sgst = sum(row.distributed_sgst for row in source_items)
        total_cess = sum(row.distributed_cess for row in source_items)
        total_cess_non_advol = sum(row.distributed_cess_non_advol for row in source_items)

        # fill the taxes table
        input_accounts = get_gst_accounts_by_type(self.company, "Input", throw=False)



        tax_type_map = {
            "igst": (input_accounts.igst_account, total_igst),
            "cgst": (input_accounts.cgst_account, total_cgst),
            "sgst": (input_accounts.sgst_account, total_sgst),
            "cess": (input_accounts.cess_account, total_cess),
            "cess_non_advol": (input_accounts.cess_non_advol_account, total_cess_non_advol),
        }

        self.tax_items = []
        for gst_tax_type, (account_head, tax_amount) in tax_type_map.items():
            if not account_head:
                continue
            self.append("tax_items", {
                "account_head": account_head,
                "gst_tax_type": gst_tax_type,
                "tax_amount": tax_amount,
            })

        self.total_eligible = sum(
            row.distributed_igst + row.distributed_cgst + row.distributed_sgst + row.distributed_cess
            for row in source_items if not row.is_ineligible_for_itc
        )
        self.total_ineligible = sum(
            row.distributed_igst + row.distributed_cgst + row.distributed_sgst + row.distributed_cess
            for row in source_items if row.is_ineligible_for_itc
        )

    @frappe.whitelist()
    def get_purchase_invoices(self, purchase_invoices: list, distribution_ratio: float = 0.0):
        """Get purchase invoices with eligible/ineligible taxes for source items table

        purchase_invoices -- list of purchase invoice IDs
        distribution_ratio -- distribution ratio to be applied
        Action: fetches source items and fills the source items table in ISD Invoice
        """

        if not purchase_invoices:
            frappe.msgprint(_("No Purchase Invoices selected"))
            return []


        frappe.has_permission("Purchase Invoice", "read", throw=True)
        frappe.has_permission("ISD Invoice", "write", throw=True)

        existing_items = [(item.purchase_invoice, item.is_ineligible_for_itc) for item in self.get("source_items") if item.purchase_invoice]
        items_to_add = self.get_source_items_from_purchase_invoices(purchase_invoices)

        if not existing_items:
            existing_items = []

        for item in items_to_add:
            if (item.purchase_invoice, item.is_ineligible_for_itc) not in existing_items:
                self.append("source_items", {**item, "distribution_ratio": distribution_ratio })

        self.calculate_distribution()
        self.calculate_taxes_and_totals()

    @frappe.whitelist()
    def get_source_items_from_purchase_invoices(self, purchase_invoices: list):
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
def create_inter_company_invoice(source_name: str):
    doc = frappe.get_doc("ISD Invoice", source_name)

    if not (doc.docstatus == 1 and doc.is_multi_company_setup and not doc.inter_company_invoice_reference):
        frappe.throw(_("Cannot create Inter Company ISD Invoice for this document."))

    new_direction = "Inward" if doc.invoice_direction == "Outward" else "Outward"
    new_party_type = "Customer" if new_direction == "Outward" else "Supplier"

    new_company = frappe.get_value(doc.party_type, doc.party_name, "represents_company")
    if not new_company:
        frappe.throw(_("{0} {1} does not represent a Company.").format(doc.party_type, doc.party_name))

    internal_field = "is_internal_customer" if new_party_type == "Customer" else "is_internal_supplier"
    new_party_name = frappe.get_value(
        new_party_type,
        {"represents_company": doc.company, internal_field: 1},
        "name",
    )
    if not new_party_name:
        frappe.throw(_("No {0} found representing {1}.").format(new_party_type, doc.company))

    new_doc = frappe.new_doc("ISD Invoice")
    new_doc.update({
        "naming_series": doc.naming_series,
        "is_credit_note": doc.is_credit_note,
        "correction_reason": doc.correction_reason,
        "posting_date": doc.posting_date,
        "cost_center": doc.cost_center,
        "distribution_ratio": doc.distribution_ratio,
        "credit_note_against": doc.credit_note_against,
        "project": doc.project,
        "is_multi_company_setup": 1,
        "invoice_direction": new_direction,
        "party_type": new_party_type,
        "company": new_company,
        "party_name": new_party_name,
        "inter_company_invoice_reference": doc.name,
        # TODO: address copy logic remaining
        "company_address": "",
        "party_address": "",
    })

    source_item_fields = [
        "purchase_invoice", "is_ineligible_for_itc", "distribution_ratio",
        "total_igst", "total_cgst", "total_sgst", "total_cess", "total_cess_non_advol",
        "distributed_igst", "distributed_cgst", "distributed_sgst",
        "distributed_cess", "distributed_cess_non_advol",
    ]
    for row in doc.source_items:
        new_doc.append("source_items", {f: row.get(f) for f in source_item_fields})

    # trigger calculation of taxes and totals in new doc
    new_doc.calculate_taxes_and_totals()

    return new_doc.as_dict()


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
