# Copyright (c) 2023, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.mapper import get_mapped_doc

from india_compliance.gst_india.utils import get_gst_accounts_by_type


class BillofEntry(Document):
    def before_validate(self):
        self.update_totals()

    def before_submit(self):
        self.validate_purchase_invoice()

    def on_submit(self):
        # self.update_purchase_invoice()
        # self.create_gl_entries()
        pass

    def on_cancel(self):
        # self.update_purchase_invoice()
        # self.cancel_gl_entries()
        pass

    def update_totals(self):
        total_customs_duty = 0
        total_taxable_value = 0

        for item in self.items:
            item.taxable_value = item.assessable_value + item.customs_duty
            total_customs_duty += item.customs_duty
            total_taxable_value += item.taxable_value

        self.total_customs_duty = total_customs_duty
        self.total_taxable_value = total_taxable_value

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
        target.customs_account = company.default_customs_duty_account
        target.paid_through_account = company.default_bank_account

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
