# Copyright (c) 2017, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate

from india_compliance.gst_india.api import set_session
from india_compliance.gst_india.constants import GST_ACCOUNT_FIELDS
from india_compliance.gst_india.constants.custom_fields import (
    E_INVOICE_FIELDS,
    E_WAYBILL_FIELDS,
    SALES_REVERSE_CHARGE_FIELDS,
)
from india_compliance.gst_india.utils import toggle_custom_fields


class GSTSettings(Document):
    def validate(self):
        self.validate_gst_accounts()
        self.validate_e_invoice_applicability_date()
        self.update_dependant_fields()
        self.validate_credentials()
        self.clear_gst_auth_session()

    def clear_gst_auth_session(self):
        previous = self.get_doc_before_save()
        if previous and not previous.api_secret and self.api_secret:
            set_session(None)

    def update_dependant_fields(self):
        if not self.api_secret:
            self.enable_api = 0

        if not self.enable_api:
            self.enable_e_invoice = 0

        if self.attach_e_waybill_print:
            self.fetch_e_waybill_data = 1

        if self.enable_e_invoice and self.auto_generate_e_invoice:
            self.auto_generate_e_waybill = 1

    def on_update(self):
        self.update_custom_fields()

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
            toggle_custom_fields(E_WAYBILL_FIELDS, self.enable_e_waybill)

        if self.has_value_changed("enable_e_invoice"):
            toggle_custom_fields(E_INVOICE_FIELDS, self.enable_e_invoice)

        if self.has_value_changed("enable_reverse_charge_in_sales"):
            toggle_custom_fields(
                SALES_REVERSE_CHARGE_FIELDS, self.enable_reverse_charge_in_sales
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

    def validate_credentials(self):
        if (
            self.enable_api
            and (self.enable_e_invoice or self.enable_e_waybill)
            and all(
                credential.service != "e-Waybill / e-Invoice"
                for credential in self.credentials
            )
        ):
            frappe.msgprint(
                # TODO: Add Link to Documentation.
                _(
                    "Please set credentials for e-Waybill / e-Invoice to use API"
                    " features"
                ),
                indicator="yellow",
                alert=True,
            )
