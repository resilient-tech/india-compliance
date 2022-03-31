# Copyright (c) 2017, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import os

import frappe
from frappe import _
from frappe.contacts.doctype.contact.contact import get_default_contact
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.model.document import Document
from frappe.utils import date_diff, get_url, nowdate

from india_compliance.gst_india.constants import GST_ACCOUNT_FIELDS


class GSTSettings(Document):
    def validate(self):
        self.validate_gst_accounts()
        self.enable_disable_reverse_charge_feature()

    def on_update(self):
        # clear session boot cache
        frappe.cache().delete_keys("bootinfo")

    def validate_gst_accounts(self):
        account_list = []
        company_wise_account_types = {}

        for row in self.gst_accounts:

            # Validate Duplicate Accounts
            for fieldname in GST_ACCOUNT_FIELDS:
                account = row.get(fieldname)
                if not account:
                    continue

                if account in account_list:
                    frappe.throw(
                        _("Row #{0}: Account {1} appears multiple times").format(
                            row.idx,
                            frappe.bold(account),
                        )
                    )

                account_list.append(account)

            # Validate Duplicate Account Types for each Company
            account_types = company_wise_account_types.setdefault(row.company, [])
            if row.account_type in account_types:
                frappe.throw(
                    _(
                        "Row #{0}: Account Type {1} appears multiple times for {2}"
                    ).format(
                        row.idx,
                        frappe.bold(row.account_type),
                        frappe.bold(row.company),
                    )
                )

            account_types.append(row.account_type)

    def enable_disable_reverse_charge_feature(self):
        self.create_reverse_charge_field_in_si() if self.enable_reverse_charge else self.delete_reverse_charge_field_from_si()

    def create_reverse_charge_field_in_si(self):

        REVERSE_CHARGE_FIELD = {
            "Sales Invoice": [
                {
                    "fieldname": "is_reverse_charge",
                    "label": "Is Reverse Charge",
                    "fieldtype": "Check",
                    "insert_after": "is_debit_note",
                    "print_hide": 1,
                    "default": 0,
                },
            ]
        }

        create_custom_fields(REVERSE_CHARGE_FIELD, update=True)
        frappe.msgprint(
            _("`Is Reverse Charge` has been created in Sales Invoice"),
            indicator="green",
            alert=True,
        )

    def delete_reverse_charge_field_from_si(self):
        doctype = "Sales Invoice"
        frappe.db.delete(
            "Custom Field", {"dt": doctype, "fieldname": "is_reverse_charge"}
        )

        frappe.msgprint(
            _("`Is Reverse Charge` has been deleted from Sales Invoice"),
            indicator="green",
            alert=True,
        )
