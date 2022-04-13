# Copyright (c) 2017, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.model.document import Document
from frappe.utils import getdate

from india_compliance.gst_india.constants import GST_ACCOUNT_FIELDS
from india_compliance.gst_india.constants.e_invoice import E_INVOICE_FIELDS
from india_compliance.gst_india.constants.e_waybill import E_WAYBILL_FIELDS
from india_compliance.gst_india.utils import delete_custom_fields


class GSTSettings(Document):
    def validate(self):
        self.validate_gst_accounts()
        self.validate_e_invoice_applicability_date()
        self.update_dependant_fields()

    def update_dependant_fields(self):
        if not self.api_secret:
            self.enable_api = 0

        if not self.enable_api:
            self.enable_e_invoice = 0
            self.fetch_e_waybill_data = 0
            self.attach_e_waybill_print = 0
            self.auto_generate_e_waybill = 0

        if not self.enable_e_waybill:
            self.enable_e_waybill_from_dn = 0

        if not self.enable_e_invoice:
            self.auto_generate_e_invoice = 0

        if self.attach_e_waybill_print:
            self.fetch_e_waybill_data = 1

        if self.enable_e_invoice and self.auto_generate_e_invoice:
            self.auto_generate_e_waybill = 1

    def on_update(self):
        frappe.enqueue(self.update_custom_fields, queue="short", at_front=True)

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

    def update_custom_fields(self):
        if self.has_value_changed("enable_e_waybill"):
            _update_custom_fields(E_WAYBILL_FIELDS, self.enable_e_waybill)

        if self.has_value_changed("enable_e_invoice"):
            _update_custom_fields(
                E_INVOICE_FIELDS, self.enable_e_invoice and self.enable_api
            )

    def validate_e_invoice_applicability_date(self):
        if not self.enable_api or not self.enable_e_invoice:
            return

        if not self.e_invoice_applicable_from:
            frappe.throw(
                _("{0} is mandatory for enabling e-Invoice").format(
                    frappe.bold(self.meta.get_label("e_invoice_applicable_from"))
                )
            )

        if getdate(self.e_invoice_applicable_from) < getdate("2021-01-01"):
            frappe.throw(
                _("{0} cannot be before 2021-01-01").format(
                    frappe.bold(self.meta.get_label("e_invoice_applicable_from"))
                )
            )


def _update_custom_fields(fields, condition):
    if condition:
        create_custom_fields(fields, ignore_validate=True)
    else:
        delete_custom_fields(fields)
