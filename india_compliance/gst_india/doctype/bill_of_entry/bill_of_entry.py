# Copyright (c) 2023, Resilient Tech and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.mapper import get_mapped_doc
from frappe.utils import today
import erpnext
from erpnext.accounts.general_ledger import make_gl_entries
from erpnext.controllers.accounts_controller import AccountsController

from india_compliance.gst_india.utils import get_gst_accounts_by_type, send_updated_doc


class BillofEntry(Document):
    def onload(self):
        if self.docstatus != 1:
            return

        existing_journal_entry = frappe.db.get_value(
            "Journal Entry Account",
            {
                "reference_type": "Bill of Entry",
                "reference_name": self.name,
                "docstatus": 1,
            },
            "name",
        )

        if existing_journal_entry:
            self.set_onload("existing_journal_entry", existing_journal_entry)

    def before_validate(self):
        self.set_item_wise_tax_rates()
        self.calculate_totals()

    def before_submit(self):
        self.validate_purchase_invoice()
        self.validate_taxes()

    def on_submit(self):
        # self.update_purchase_invoice()
        self.create_gl_entries()

    def on_cancel(self):
        self.ignore_linked_doctypes = ("GL Entry",)
        self.cancel_gl_entries()

    def on_trash(self):
        controller = AccountsController
        controller.on_trash(self)

    def set_defaults(self):
        company = frappe.get_cached_doc("Company", self.company)
        self.customs_expense_account = company.default_customs_expense_account
        self.customs_payable_account = company.default_customs_payable_account

    @frappe.whitelist()
    def set_taxes_and_totals(self):
        self.set_item_wise_tax_rates()
        self.calculate_totals()

    def calculate_totals(self):
        self.set_total_customs_and_taxable_values()
        self.set_total_taxes()
        self.total_amount_payable = self.total_customs_duty + self.total_taxes

    def set_total_customs_and_taxable_values(self):
        total_customs_duty = 0
        total_taxable_value = 0

        for item in self.items:
            item.taxable_value = item.assessable_value + item.customs_duty
            total_customs_duty += item.customs_duty
            total_taxable_value += item.taxable_value

        self.total_customs_duty = total_customs_duty
        self.total_taxable_value = total_taxable_value

    def set_total_taxes(self):
        total_taxes = 0

        for tax in self.taxes:
            if tax.charge_type == "On Net Total":
                tax.tax_amount = self.get_tax_amount(tax.item_wise_tax_rates)

            total_taxes += tax.tax_amount
            tax.total = self.total_taxable_value + total_taxes

        self.total_taxes = total_taxes

    def get_tax_amount(self, item_wise_tax_rates):
        if type(item_wise_tax_rates) == str:
            item_wise_tax_rates = json.loads(item_wise_tax_rates)

        tax_amount = 0
        for item in self.items:
            tax_amount += (
                item_wise_tax_rates.get(item.name, 0) * item.taxable_value / 100
            )

        return tax_amount

    def validate_purchase_invoice(self):
        purchase = frappe.get_doc("Purchase Invoice", self.purchase_invoice)
        if purchase.docstatus != 1:
            frappe.throw(
                _("Purchase Invoice must be submitted before submitting Bill of Entry")
            )

        if purchase.gst_category != "Overseas":
            frappe.throw(
                _(
                    "Purchase Invoice must be of Overseas category to create Bill of"
                    " Entry"
                )
            )

        pi_items = [item.name for item in purchase.items]
        for item in self.items:
            if item.pi_detail not in pi_items:
                frappe.throw(
                    _(
                        "Purchase Invoice Item {0} not found in Purchase Invoice {1}"
                    ).format(item.pi_detail, self.purchase_invoice)
                )

    def validate_taxes(self):
        input = get_gst_accounts_by_type(self.company, "Input", throw=True)
        for tax in self.taxes:
            if tax.account_head in [input.igst_account, input.cess_account]:
                continue

            if tax.tax_amount != 0:
                frappe.throw(
                    _(
                        "Row#: {0}. Only Input IGST and CESS accounts are allowed in"
                        " Bill of Entry"
                    ).format(frappe.bold(tax.idx))
                )

    def create_gl_entries(self):
        gl_entries = self.get_gl_entries()
        if gl_entries:
            make_gl_entries(gl_entries, cancel=0, adv_adj=0)

    def cancel_gl_entries(self):
        gl_entries = self.get_gl_entries()
        if gl_entries:
            make_gl_entries(gl_entries, cancel=1, adv_adj=0)

    def get_gl_entries(self):
        gl_entries = []
        remarks = "No Remarks"
        self.company_currency = erpnext.get_company_currency(self.company)
        controller = AccountsController

        for item in self.items:
            gl_entries.append(
                controller.get_gl_dict(
                    self,
                    {
                        "account": self.customs_expense_account,
                        "debit": item.customs_duty,
                        "credit": 0,
                        "cost_center": item.cost_center,
                        "remarks": remarks,
                    },
                )
            )

        for tax in self.taxes:
            gl_entries.append(
                controller.get_gl_dict(
                    self,
                    {
                        "account": tax.account_head,
                        "debit": tax.tax_amount,
                        "credit": 0,
                        "cost_center": self.cost_center,
                        "remarks": remarks,
                    },
                )
            )

        gl_entries.append(
            controller.get_gl_dict(
                self,
                {
                    "account": self.customs_payable_account,
                    "debit": 0,
                    "credit": self.total_amount_payable,
                    "cost_center": self.cost_center,
                    "remarks": remarks,
                },
            )
        )

        return gl_entries

    def validate_account_currency(self, *args):
        # Overriding AccountsController method
        pass

    @frappe.whitelist()
    def set_item_wise_tax_rates(self, item_name=None, tax_name=None):
        items, taxes = self.get_rows_to_update(item_name, tax_name)

        tax_templates = list({item.item_tax_template for item in items})
        tax_accounts = list({tax.account_head for tax in taxes})

        if not tax_accounts:
            return

        item_tax_map = self.get_item_tax_map(tax_templates, tax_accounts)

        for tax in taxes:
            if tax.charge_type != "On Net Total":
                tax.item_wise_tax_rates = "{}"
                continue

            item_wise_tax_rates = json.loads(tax.item_wise_tax_rates or "{}")

            for item in items:
                key = (item.item_tax_template, tax.account_head)
                if key in item_tax_map:
                    tax_rate = item_tax_map[key]
                    item_wise_tax_rates[item.name] = tax_rate

                else:
                    item_wise_tax_rates[item.name] = tax.rate

            tax.item_wise_tax_rates = json.dumps(item_wise_tax_rates)

        return send_updated_doc(self)

    def get_item_tax_map(self, tax_templates, tax_accounts):
        """
        Parameters:
            tax_templates (list): List of item tax templates used in the items
            tax_accounts (list): List of tax accounts used in the taxes

        Returns:
            dict: A map of item_tax_template, tax_account and tax_rate

        Sample Output:
            {
                ('GST 18%', 'IGST - TC'): 18.0
                ('GST 28%', 'IGST - TC'): 28.0
            }
        """
        item_tax_map = {}

        if tax_templates:
            template_detail = frappe.get_all(
                "Item Tax Template Detail",
                fields=["parent", "tax_type", "tax_rate"],
                filters={
                    "parent": ["in", tax_templates],
                    "tax_type": ["in", tax_accounts],
                },
            )
            item_tax_map = {(d.parent, d.tax_type): d.tax_rate for d in template_detail}

        return item_tax_map

    def get_rows_to_update(self, item_name, tax_name):
        """
        Returns items and taxes to update based on item_name and tax_name passed.
        If item_name and tax_name are not passed, all items and taxes are returned.
        """

        items = [item for item in self.items if item.name == item_name] or self.items
        taxes = [tax for tax in self.taxes if tax.name == tax_name] or self.taxes

        return items, taxes


@frappe.whitelist()
def make_bill_of_entry(source_name, target_doc=None):
    def add_default_taxes(source, target):
        target.posting_date = today()
        input_igst_account = get_gst_accounts_by_type(
            source.company, "Input"
        ).igst_account

        if not input_igst_account:
            return

        rate, description = frappe.db.get_value(
            "Purchase Taxes and Charges",
            {
                "parenttype": "Purchase Taxes and Charges Template",
                "account_head": input_igst_account,
            },
            ["rate", "description"],
        ) or [0, input_igst_account]

        # Remove existing taxes and add default tax
        target.taxes = []
        target.append(
            "taxes",
            {
                "charge_type": "On Net Total",
                "account_head": input_igst_account,
                "rate": rate,
                "description": description,
            },
        )

        target.set_defaults()

    doc = get_mapped_doc(
        "Purchase Invoice",
        source_name,
        {
            "Purchase Invoice": {
                "doctype": "Bill of Entry",
                "validation": {
                    "docstatus": ["=", 1],
                    "gst_category": ["=", "Overseas"],
                },
            },
            "Purchase Invoice Item": {
                "doctype": "Bill of Entry Item",
                "field_map": {
                    "name": "pi_detail",
                    "taxable_value": "assessable_value",
                },
            },
        },
        target_doc,
        postprocess=add_default_taxes,
    )

    return doc


@frappe.whitelist()
def make_journal_entry_for_payment(source_name, target_doc=None):
    def set_missing_values(source, target):
        target.voucher_type = "Bank Entry"
        target.posting_date = today()
        target.cheque_date = today()
        target.user_remark = "Payment against Bill of Entry {0}".format(source.name)

        company = frappe.get_cached_doc("Company", source.company)
        target.append(
            "accounts",
            {
                "account": source.customs_payable_account,
                "debit_in_account_currency": source.total_amount_payable,
                "reference_type": "Bill of Entry",
                "reference_name": source.name,
                "cost_center": company.cost_center,
            },
        )

        target.append(
            "accounts",
            {
                "account": company.default_bank_account or company.default_cash_account,
                "credit_in_account_currency": source.total_amount_payable,
                "cost_center": company.cost_center,
            },
        )

    doc = get_mapped_doc(
        "Bill of Entry",
        source_name,
        {
            "Bill of Entry": {
                "doctype": "Journal Entry",
                "validation": {
                    "docstatus": ["=", 1],
                },
            },
        },
        target_doc,
        postprocess=set_missing_values,
    )

    return doc


@frappe.whitelist()
def make_landed_cost_voucher(source_name, target_doc=None):
    def set_missing_values(source, target):
        items = get_items_for_landed_cost_voucher(source)
        if not items:
            frappe.throw(_("No items found for Landed Cost Voucher"))

        target.posting_date = today()
        target.distribute_charges_based_on = "Distribute Manually"

        # add references
        reference_docs = {item.parent: item.parenttype for item in items.values()}
        for parent, parenttype in reference_docs.items():
            target.append(
                "purchase_receipts",
                {
                    "receipt_document_type": parenttype,
                    "receipt_document": parent,
                },
            )

        # add items
        target.get_items_from_purchase_receipts()

        # update applicable charges
        total_customs_duty = 0
        for item in target.items:
            item.applicable_charges = items[item.purchase_receipt_item].customs_duty
            total_customs_duty += item.applicable_charges

        # add taxes
        target.append(
            "taxes",
            {
                "expense_account": source.customs_expense_account,
                "description": "Customs Duty",
                "amount": total_customs_duty,
            },
        )

        if total_customs_duty != source.total_customs_duty:
            frappe.msgprint(
                _(
                    "Could not find purchase receipts for all items. Please check"
                    " manually."
                )
            )

    doc = get_mapped_doc(
        "Bill of Entry",
        source_name,
        {
            "Bill of Entry": {
                "doctype": "Landed Cost Voucher",
            },
        },
        target_doc,
        postprocess=set_missing_values,
    )

    return doc


def get_items_for_landed_cost_voucher(boe):
    """
    For creating landed cost voucher, it needs to be linked with transaction where stock was updated.
    This function will return items based on following conditions:
        1. Where stock was updated in Purchase Invoice
        2. Where stock was updated in Purchase Receipt
            a. Purchase Invoice was created from Purchase Receipt
            b. Purchase Receipt was created from Purchase Invoice

    Also, it will apportion customs duty for PI items.

    NOTE: Assuming business has consistent practice of creating PR and PI
    """
    pi = frappe.get_doc("Purchase Invoice", boe.purchase_invoice)
    item_customs_map = {item.pi_detail: item.customs_duty for item in boe.items}

    def _item_dict(items):
        return frappe._dict({item.name: item for item in items})

    # No PR
    if pi.update_stock:
        pi_items = [pi_item.as_dict() for pi_item in pi.items]
        for pi_item in pi_items:
            pi_item.customs_duty = item_customs_map.get(pi_item.name)

        return _item_dict(pi_items)

    # Creating PI from PR
    if pi.items[0].purchase_receipt:
        pr_pi_map = {pi_item.pr_detail: pi_item.name for pi_item in pi.items}
        pr_items = frappe.get_all(
            "Purchase Receipt Item",
            fields="*",
            filters={"name": ["in", pr_pi_map.keys()], "docstatus": 1},
        )

        for pr_item in pr_items:
            pr_item.customs_duty = item_customs_map.get(pr_pi_map.get(pr_item.name))

        return _item_dict(pr_items)

    # Creating PR from PI (Qty split possible in PR)
    pr_items = frappe.get_all(
        "Purchase Receipt Item",
        fields="*",
        filters={"purchase_invoice": pi.name, "docstatus": 1},
    )

    item_qty_map = {item.name: item.qty for item in pi.items}

    for pr_item in pr_items:
        customs_duty_for_item = item_customs_map.get(pr_item.purchase_invoice_item)
        total_qty = item_qty_map.get(pr_item.purchase_invoice_item)
        pr_item.customs_duty = customs_duty_for_item * pr_item.qty / total_qty

    return _item_dict(pr_items)
