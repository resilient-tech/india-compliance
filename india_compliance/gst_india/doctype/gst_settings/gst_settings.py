# Copyright (c) 2017, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate

from india_compliance.gst_india.constants import GST_ACCOUNT_FIELDS, GST_PARTY_TYPES
from india_compliance.gst_india.constants.custom_fields import (
    E_INVOICE_FIELDS,
    E_WAYBILL_FIELDS,
    SALES_REVERSE_CHARGE_FIELDS,
)
from india_compliance.gst_india.page.india_compliance_account import (
    _disable_api_promo,
    post_login,
)
from india_compliance.gst_india.utils import can_enable_api, is_api_enabled
from india_compliance.gst_india.utils.custom_fields import toggle_custom_fields
from india_compliance.gst_india.utils.gstin_info import get_gstin_info

E_INVOICE_START_DATE = "2021-01-01"


class GSTSettings(Document):
    def onload(self):
        if is_api_enabled(self) and frappe.db.get_global("has_missing_gst_category"):
            self.set_onload("has_missing_gst_category", True)

        if not (can_enable_api(self) or frappe.db.get_global("ic_api_promo_dismissed")):
            self.set_onload("can_show_promo", True)

    def validate(self):
        self.update_dependant_fields()
        self.validate_enable_api()
        self.validate_gst_accounts()
        self.validate_e_invoice_applicability_date()
        self.validate_credentials()
        self.clear_api_auth_session()
        self.update_retry_e_invoice_e_waybill_scheduled_job()

    def clear_api_auth_session(self):
        if self.has_value_changed("api_secret") and self.api_secret:
            post_login()

    def update_dependant_fields(self):
        if self.attach_e_waybill_print:
            self.fetch_e_waybill_data = 1

    def on_update(self):
        self.update_custom_fields()
        # clear session boot cache
        frappe.cache.delete_keys("bootinfo")

    def update_retry_e_invoice_e_waybill_scheduled_job(self):
        if not self.has_value_changed("enable_retry_einv_ewb_generation"):
            return

        frappe.db.set_value(
            "Scheduled Job Type",
            "e_invoice.retry_e_invoice_e_waybill_generation",
            "stopped",
            not self.enable_retry_einv_ewb_generation,
        )

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

        if (
            not self.e_invoice_applicable_from
            and not self.apply_e_invoice_only_for_selected_companies
        ):
            frappe.throw(
                _("{0} is mandatory for enabling e-Invoice").format(
                    frappe.bold(self.meta.get_label("e_invoice_applicable_from"))
                )
            )

        if self.e_invoice_applicable_from and (
            getdate(self.e_invoice_applicable_from) < getdate(E_INVOICE_START_DATE)
        ):
            frappe.throw(
                _("{0} date cannot be before {1}").format(
                    frappe.bold(self.meta.get_label("e_invoice_applicable_from")),
                    E_INVOICE_START_DATE,
                )
            )

        if self.apply_e_invoice_only_for_selected_companies:
            self.validate_e_invoice_applicable_companies()

    def validate_credentials(self):
        if not self.enable_api:
            return

        for credential in self.credentials:
            if credential.service == "Returns":
                self.validate_app_key(credential)
                continue

            if credential.password:
                continue

            frappe.throw(
                _(
                    "Row #{0}: Password is required when setting a GST Credential"
                    " for {1}"
                ).format(credential.idx, credential.service),
                frappe.MandatoryError,
                _("Missing Required Field"),
            )

        if (self.enable_e_invoice or self.enable_e_waybill) and all(
            credential.service != "e-Waybill / e-Invoice"
            for credential in self.credentials
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

    def validate_app_key(self, credential):
        if not credential.app_key or len(credential.app_key) != 32:
            credential.app_key = frappe.generate_hash(length=32)

    def validate_enable_api(self):
        if (
            self.enable_api
            and self.has_value_changed("enable_api")
            and not can_enable_api(self)
        ):
            frappe.throw(
                _(
                    "Please counfigure your India Compliance Account to "
                    "enable API features"
                )
            )

        if (
            self.sandbox_mode
            and self.autofill_party_info
            and self.has_value_changed("sandbox_mode")
        ):
            frappe.msgprint(
                _(
                    "Autofill Party Information based on GSTIN is not supported in"
                    " sandbox mode"
                ),
            )

    def validate_e_invoice_applicable_companies(self):
        if not self.e_invoice_applicable_companies:
            frappe.throw(
                _(
                    "You must select at least one company to which e-Invoice is"
                    " Applicable"
                )
            )

        company_list = []
        for row in self.e_invoice_applicable_companies:
            if not row.applicable_from:
                frappe.throw(
                    _("Row #{0}: {1} is mandatory for enabling e-Invoice").format(
                        row.idx, frappe.bold(row.meta.get_label("applicable_from"))
                    )
                )

            if getdate(row.applicable_from) < getdate(E_INVOICE_START_DATE):
                frappe.throw(
                    _("Row #{0}: {1} date cannot be before {2}").format(
                        row.idx,
                        frappe.bold(row.meta.get_label("applicable_from")),
                        E_INVOICE_START_DATE,
                    )
                )

            if row.company in company_list:
                frappe.throw(
                    _("Row #{0}: {1} {2} appears multiple times").format(
                        row.idx, row.meta.get_label("company"), frappe.bold(row.company)
                    )
                )

            company_list.append(row.company)


@frappe.whitelist()
def disable_api_promo():
    if frappe.has_permission("GST Settings", "write"):
        _disable_api_promo()


@frappe.whitelist()
def enqueue_update_gst_category():
    frappe.has_permission("GST Settings", "write", throw=True)
    frappe.enqueue(update_gst_category, queue="long", timeout=6000)
    frappe.msgprint(
        _("Updating GST Category in background"),
        alert=True,
    )


def update_gst_category():
    if not is_api_enabled():
        return

    # get all Addresses with linked party
    address_without_category = frappe.get_all(
        "Address",
        fields=("name", "gstin"),
        filters={
            "link_doctype": ("in", GST_PARTY_TYPES),
            "link_name": ("!=", ""),
            "gst_category": ("in", ("", None)),
        },
    )

    # party-wise addresses
    category_map = {}
    for address in address_without_category:
        gstin_info = get_gstin_info(address.gstin)
        gst_category = gstin_info.gst_category

        category_map.setdefault(gst_category, []).append(address.name)

    for gst_category, addresses in category_map.items():
        frappe.db.set_value(
            "Address", {"name": ("in", addresses)}, "gst_category", gst_category
        )

    frappe.db.set_global("has_missing_gst_category", None)
