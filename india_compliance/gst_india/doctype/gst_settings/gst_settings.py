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
from india_compliance.gst_india.constants.e_waybill import E_WAYBILL_FIELDS
from india_compliance.gst_india.utils import delete_custom_fields


class GSTSettings(Document):
    def validate(self):
        self.validate_gst_accounts()

    def on_update(self):
        # clear session boot cache
        frappe.cache().delete_keys("bootinfo")
        frappe.enqueue(self.create_or_delete_fields)

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

    def create_or_delete_fields(self):
        if not self.has_value_changed("enable_e_waybill"):
            return

        if self.enable_e_waybill:
            create_custom_fields(E_WAYBILL_FIELDS, update=True)
        else:
            delete_custom_fields(E_WAYBILL_FIELDS)
