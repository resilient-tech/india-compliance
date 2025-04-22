# Copyright (c) 2017, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.query_builder.functions import IfNull
from frappe.utils import add_to_date, getdate

from india_compliance.gst_india.constants import (
    GST_ACCOUNT_FIELDS,
    GST_PARTY_TYPES,
    TAXABLE_GST_TREATMENTS,
)
from india_compliance.gst_india.constants.custom_fields import (
    E_INVOICE_FIELDS,
    E_WAYBILL_FIELDS,
    SALES_REVERSE_CHARGE_FIELDS,
)
from india_compliance.gst_india.doctype.gst_return_log.gst_return_log import (
    add_comment_to_gst_return_log,
    update_is_not_latest_gstr1_data,
)
from india_compliance.gst_india.doctype.gstin.gstin import get_gstr_1_filed_upto
from india_compliance.gst_india.page.india_compliance_account import (
    _disable_api_promo,
    post_login,
)
from india_compliance.gst_india.utils import (
    can_enable_api,
    is_api_enabled,
    is_production_api_enabled,
)
from india_compliance.gst_india.utils.gstin_info import get_gstin_info
from india_compliance.utils.custom_fields import toggle_custom_fields

E_INVOICE_START_DATE = "2021-01-01"


class GSTSettings(Document):
    def onload(self):
        if is_api_enabled(self) and frappe.db.get_global("has_missing_gst_category"):
            self.set_onload("has_missing_gst_category", True)

        if not (can_enable_api(self) or frappe.db.get_global("ic_api_promo_dismissed")):
            self.set_onload("can_show_promo", True)

    def validate(self):
        self.update_dependant_fields()

        if not frappe.flags.in_install:
            self.validate_enable_api()
            self.validate_gst_accounts()
            self.validate_e_invoice_applicability_date()
            self.validate_credentials()
            self.validate_gstin_status_refresh_interval()

        self.clear_api_auth_session()
        self.update_retry_e_invoice_e_waybill_scheduled_job()
        self.update_e_invoice_status()

    def update_e_invoice_status(self):
        previous_doc = self.get_doc_before_save()

        fields_to_check = (
            "enable_e_invoice",
            "e_invoice_applicable_from",
            "apply_e_invoice_only_for_selected_companies",
        )

        has_value_changed = False
        for field in fields_to_check:
            if previous_doc.get(field) != self.get(field):
                has_value_changed = True
                break

        if not (
            has_value_changed
            or not self.is_child_table_same("e_invoice_applicable_companies")
        ):
            return

        frappe.enqueue(update_e_invoice_status, queue="long", timeout=6000)

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
            {
                "method": "india_compliance.gst_india.utils.e_invoice.retry_e_invoice_e_waybill_generation"
            },
            "stopped",
            not self.enable_retry_einv_ewb_generation,
        )

    def update_auto_refresh_authtoken_scheduled_job(self):
        if not self.has_value_changed("enable_auto_reconciliation"):
            return

        frappe.db.set_value(
            "Scheduled Job Type",
            {
                "method": "india_compliance.gst_india.doctype.purchase_reconciliation_tool.purchase_reconciliation_tool.auto_refresh_authtoken"
            },
            "stopped",
            not self.enable_auto_reconciliation,
        )

    def get_gstin_with_credentials(self, service=None):
        if not service:
            return

        if service == "Returns" and not self:
            return

        if service == "e-Waybill" and not self.enable_e_waybill:
            return

        if service == "e-Invoice" and not self.enable_e_invoice:
            return

        if service in ["e-Invoice", "e-Waybill"]:
            service = "e-Waybill / e-Invoice"

        for row in self.credentials:
            if row.service == service:
                return row.gstin

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

        if (
            (self.enable_e_invoice or self.enable_e_waybill)
            and not self.sandbox_mode
            and not frappe.flags.in_setup_wizard
            and all(
                credential.service != "e-Waybill / e-Invoice"
                for credential in self.credentials
            )
        ):
            frappe.msgprint(
                _(
                    "Please set credentials for e-Waybill / e-Invoice to use API"
                    " features.<br>"
                    "For more information, refer to the following documentation: {0}"
                ).format(
                    """
                <a href="https://docs.indiacompliance.app/docs/ewaybill-and-einvoice/gst_settings" target="_blank">
                    Setup Credentials for e-Waybill / e-Invoice
                </a>
                """
                ),
                indicator="yellow",
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

    def validate_gstin_status_refresh_interval(self):
        if not (
            self.enable_api
            and self.validate_gstin_status
            and self.get("gstin_status_refresh_interval", 0) < 15
        ):
            return

        self.gstin_status_refresh_interval = 15
        frappe.msgprint(
            _("GSTIN status refresh interval is set to 15"),
            alert=True,
            indicator="yellow",
        )

    def is_sek_valid(self, gstin, throw=False, threshold=30):
        for credential in self.credentials:
            if credential.service == "Returns" and credential.gstin == gstin:
                break

        else:
            if throw:
                frappe.throw(
                    _(
                        "No credential found for the GSTIN {0} in the GST Settings"
                    ).format(gstin)
                )

            return False

        if credential.session_expiry and credential.session_expiry > add_to_date(
            None, minutes=threshold * -1
        ):
            return True

    def has_valid_credentials(self, gstin, service, throw=False):
        for credential in self.credentials:
            if credential.gstin == gstin and credential.service == service:
                break
        else:
            message = _(
                "No credential found for the GSTIN {0} in the GST Settings"
            ).format(gstin)

            if throw:
                frappe.throw(message)

            return False

        return True

    # GSTR 1 UTILITY
    def is_gstr1_api_enabled(self, gstin, warn_for_missing_credentials=False):
        if not is_production_api_enabled(self):
            return False

        if not self.enable_gstr_1_api:
            return False

        if not self.has_valid_credentials(gstin, "Returns"):
            if warn_for_missing_credentials:
                frappe.publish_realtime(
                    "show_missing_gst_credentials_message",
                    dict(
                        message=_(
                            "Credentials are missing for GSTIN {0} for service"
                            " Returns in GST Settings"
                        ).format(gstin),
                        title=_("Missing Credentials"),
                    ),
                    user=frappe.session.user,
                )

            return False

        return True


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
    gstin_info_map = {}

    for address in address_without_category:
        gstin = address.gstin

        if gstin not in gstin_info_map:
            gstin_info_map[gstin] = get_gstin_info(
                gstin, doc=frappe._dict(docname="Address", name=address.name)
            )

        gst_category = gstin_info_map[gstin].gst_category

        category_map.setdefault(gst_category, []).append(address.name)

    for gst_category, addresses in category_map.items():
        frappe.db.set_value(
            "Address", {"name": ("in", addresses)}, "gst_category", gst_category
        )

    frappe.db.set_global("has_missing_gst_category", None)


def update_e_invoice_status():
    """
    - Update e-Invoice status based on Applicability
    - Update "Pending" and "Not Applicable" Status
    """

    gst_settings = frappe.get_cached_doc("GST Settings")
    if not gst_settings.enable_e_invoice:
        return update_not_applicable_status()

    if not gst_settings.apply_e_invoice_only_for_selected_companies:
        e_invoice_applicability_date = gst_settings.e_invoice_applicable_from
        update_pending_status(e_invoice_applicability_date)
        update_not_applicable_status(e_invoice_applicability_date)
        return

    companies = frappe.get_all("Company", filters={"country": "India"}, pluck="name")

    for company in companies:
        e_invoice_applicability_date = get_e_invoice_applicability_date(
            company, gst_settings, throw=False
        )

        update_pending_status(e_invoice_applicability_date, company)
        update_not_applicable_status(e_invoice_applicability_date, company)


def get_e_invoice_applicability_date(company, settings=None, throw=True):
    if not settings:
        settings = frappe.get_cached_doc("GST Settings")

    e_invoice_applicable_from = settings.e_invoice_applicable_from

    if settings.apply_e_invoice_only_for_selected_companies:
        for row in settings.e_invoice_applicable_companies:
            if company == row.company:
                e_invoice_applicable_from = row.applicable_from
                break

        else:
            return

    return e_invoice_applicable_from


def update_pending_status(e_invoice_applicability_date, company=None):
    if not e_invoice_applicability_date:
        return

    sales_invoice = frappe.qb.DocType("Sales Invoice")
    sales_invoice_item = frappe.qb.DocType("Sales Invoice Item")

    query = (
        frappe.qb.update(sales_invoice)
        .join(sales_invoice_item)
        .on(sales_invoice_item.parent == sales_invoice.name)
        .set(sales_invoice.einvoice_status, "Pending")
        .where(
            IfNull(sales_invoice.billing_address_gstin, "")
            != IfNull(sales_invoice.company_gstin, "")
        )
        .where(IfNull(sales_invoice.irn, "") == "")
        .where(sales_invoice_item.gst_treatment.isin(TAXABLE_GST_TREATMENTS))
        .where(
            (IfNull(sales_invoice.place_of_supply, "") == "96-Other Countries")
            | (IfNull(sales_invoice.billing_address_gstin, "") != "")
        )
        .where(sales_invoice.posting_date >= e_invoice_applicability_date)
        .where(sales_invoice.docstatus == 1)
        .where(IfNull(sales_invoice.company_gstin, "") != "")
        .where(sales_invoice.is_opening != "Yes")
    )

    if company:
        query = query.where(sales_invoice.company == company)

    query.run()


def update_not_applicable_status(e_invoice_applicability_date=None, company=None):
    sales_invoice = frappe.qb.DocType("Sales Invoice")
    query = (
        frappe.qb.update(sales_invoice)
        .set(sales_invoice.einvoice_status, "Not Applicable")
        .where(IfNull(sales_invoice.einvoice_status, "") == "Pending")
        .where(sales_invoice.docstatus == 1)
    )
    if e_invoice_applicability_date:
        query = query.where(sales_invoice.posting_date < e_invoice_applicability_date)

    if company:
        company = query.where(sales_invoice.company == company)

    query.run()


def restrict_gstr_1_transaction_for(doc, gst_settings=None, action="submit"):
    """
    Check if the user is allowed to modify transactions before the GSTR-1 filing date
    Additionally, update the `is_not_latest_gstr1_data` field in the GST Return Log
    """
    posting_date = getdate(doc.posting_date)

    if not gst_settings:
        gst_settings = frappe.get_cached_doc("GST Settings")

    restrict = True

    if not gst_settings.restrict_changes_after_gstr_1:
        restrict = False

    gstr_1_filed_upto = get_gstr_1_filed_upto(doc.company_gstin)

    if not gstr_1_filed_upto:
        restrict = False

    elif posting_date > getdate(gstr_1_filed_upto):
        restrict = False

    if (
        gst_settings.role_allowed_to_modify in frappe.get_roles()
        or frappe.session.user == "Administrator"
    ):
        restrict = False

    if restrict:
        return gstr_1_filed_upto

    # postprocess
    update_is_not_latest_gstr1_data(posting_date, doc.company_gstin)

    if posting_date <= getdate(gstr_1_filed_upto):
        add_comment_to_gst_return_log(doc, action)
