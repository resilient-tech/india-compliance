# Copyright (c) 2023, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.mapper import get_mapped_doc

import erpnext
from erpnext.accounts.general_ledger import make_gl_entries
from erpnext.controllers.accounts_controller import AccountsController

from india_compliance.gst_india.utils import get_gst_accounts_by_type


class BillofEntry(Document):
    def before_validate(self):
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
                tax.tax_amount = self.total_taxable_value * tax.rate / 100

            total_taxes += tax.tax_amount
            tax.total = self.total_taxable_value + total_taxes

        self.total_taxes = total_taxes

    def validate_purchase_invoice(self):
        purchase = frappe.get_doc("Purchase Invoice", self.purchase_invoice)
        if purchase.docstatus != 1:
            frappe.throw(
                _("Purchase Invoice must be submitted before submitting Bill of Entry")
            )

        if purchase.gst_category != "Overseas":
            frappe.throw(
                _(
                    "Purchase Invoice must be of Overseas category to create Bill of Entry"
                )
            )

        pi_items = [item.name for item in purchase.items]
        for item in self.items:
            if item.pi_detail not in pi_items:
                frappe.throw(
                    _(
                        "Purchase Invoice Item {0} not found in Purchase Invoice {1}".format(
                            item.pi_detail, self.purchase_invoice
                        )
                    )
                )

    def validate_taxes(self):
        input = get_gst_accounts_by_type(self.company, "Input", throw=True)
        for tax in self.taxes:
            if tax.account_head in [input.igst_account, input.cess_account]:
                continue

            if tax.tax_amount != 0:
                frappe.throw(
                    _(
                        "Row#: {0}. Only Input IGST and CESS accounts are allowed in Bill of Entry".format(
                            frappe.bold(tax.idx)
                        )
                    )
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
                        "account": self.customs_duty_account,
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
                    "account": self.payable_account,
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
def make_bill_of_entry(source_name, target_doc=None):
    def add_default_taxes(source, target):
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

        taxes = frappe.new_doc("Purchase Taxes and Charges")
        taxes.update(
            {
                "charge_type": "On Net Total",
                "account_head": input_igst_account,
                "rate": rate,
                "description": description,
            }
        )
        target.taxes = [taxes]

        # Default accounts
        company = frappe.get_cached_doc("Company", source.company)
        target.customs_duty_account = company.default_customs_duty_account

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
