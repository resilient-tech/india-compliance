# Copyright (c) 2022, Resilient Tech and contributors
# For license information, please see license.txt

from calendar import monthrange
from datetime import date
from math import ceil
from typing import List

from dateutil.rrule import MONTHLY, rrule
from rapidfuzz import fuzz, process

import frappe
from frappe.model.document import Document
from frappe.query_builder import Case
from frappe.query_builder.functions import Abs, Sum
from frappe.utils import add_months, getdate, rounded

from india_compliance.gst_india.constants import GST_TAX_TYPES, ORIGINAL_VS_AMENDED
from india_compliance.gst_india.utils import (
    get_gst_accounts_by_type,
    get_json_from_file,
    get_party_for_gstin,
)
from india_compliance.gst_india.utils.exporter import ExcelExporter
from india_compliance.gst_india.utils.gstr import (
    GSTRCategory,
    ReturnType,
    download_gstr_2a,
    download_gstr_2b,
    save_gstr_2a,
    save_gstr_2b,
)

GSTR2B_GEN_DATE = 14


class PurchaseReconciliationTool(Document):
    FIELDS_TO_MATCH = {
        "fy": "Financial Year",
        "supplier_gstin": "GSTIN",
        "bill_no": "Bill No",
        "place_of_supply": "Place of Supply",
        "is_reverse_charge": "Reverse Charge",
        "cgst": "CGST",
        "sgst": "SGST",
        "igst": "IGST",
        "cess": "CESS",
        "taxable_value": "Taxable Amount",
    }
    FIELDS_LIST = list(FIELDS_TO_MATCH.keys())
    GSTIN_RULES = [
        {"Exact Match": ["E", "E", "E", "E", "E", 0, 0, 0, 0, 0]},
        {"Suggested Match": ["E", "E", "F", "E", "E", 0, 0, 0, 0, 0]},
        {"Suggested Match": ["E", "E", "E", "E", "E", 1, 1, 1, 1, 2]},
        {"Suggested Match": ["E", "E", "F", "E", "E", 1, 1, 1, 1, 2]},
        {"Mismatch": ["E", "E", "E", "N", "N", "N", "N", "N", "N", "N"]},
        {"Mismatch": ["E", "E", "F", "N", "N", "N", "N", "N", "N", "N"]},
        {"Residual Match": ["E", "E", "N", "E", "E", 1, 1, 1, 1, 2]},
    ]

    PAN_RULES = [
        {"Mismatch": ["E", "N", "E", "E", "E", 1, 1, 1, 1, 2]},
        {"Mismatch": ["E", "N", "F", "E", "E", 1, 1, 1, 1, 2]},
        {"Mismatch": ["E", "N", "F", "N", "N", "N", "N", "N", "N", "N"]},
        {"Residual Match": ["E", "N", "N", "E", "E", 1, 1, 1, 1, 2]},
    ]

    GST_CATEGORIES = {
        "Registered Regular": "B2B",
        "SEZ": "IMPGSEZ",
        "Overseas": "IMPG",
        "UIN Holders": "B2B",
        "Tax Deductor": "B2B",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.GSTR2 = frappe.qb.DocType("GST Inward Supply")
        self.GSTR2_ITEM = frappe.qb.DocType("GST Inward Supply Item")
        self.PI = frappe.qb.DocType("Purchase Invoice")
        self.PI_TAX = frappe.qb.DocType("Purchase Taxes and Charges")
        self.PI_ITEM = frappe.qb.DocType("Purchase Invoice Item")

    def onload(self):
        if hasattr(self, "reconciliation_data"):
            self.set_onload("reconciliation_data", self.reconciliation_data)

    def validate(self):
        # set inward_supply_from_date to first day of the month
        date = getdate(self.inward_supply_from_date)
        self.inward_supply_from_date = _get_first_day(date.month, date.year)
        self.gstin_party_map = frappe._dict()

    def on_update(self):
        # reconcile purchases and inward supplies
        if frappe.flags.in_install or frappe.flags.in_migrate:
            return

        for row in ORIGINAL_VS_AMENDED:
            self.reconcile(row["original"], row["amended"])

        self.reconciliation_data = self.get_reconciliation_data()

    def reconcile(self, category, amended_category):
        """
        Reconcile purchases and inward supplies for given category.
        """
        # GSTIN Level matching
        purchases = self.get_purchase(category)
        inward_supplies = self.get_inward_supply(category, amended_category)
        self._reconcile(self.GSTIN_RULES, purchases, inward_supplies, category)

        # PAN Level matching
        purchases = self.get_pan_level_data(purchases)
        inward_supplies = self.get_pan_level_data(inward_supplies)
        self._reconcile(self.PAN_RULES, purchases, inward_supplies, category)

    def _reconcile(self, rules, purchases, inward_supplies, category):
        if not (purchases and inward_supplies):
            return

        for rule_map in rules:
            for match_status, rules in rule_map.items():
                self.reconcile_for_rule(
                    purchases, inward_supplies, match_status, rules, category
                )

    def reconcile_for_rule(
        self, purchases, inward_supplies, match_status, rules, category
    ):
        """
        Sequentially reconcile invoices as per rules list.
        - Reconciliation only done between invoices of same GSTIN.
        - Where a match is found, update Inward Supply and Purchase Invoice.
        """

        for supplier_gstin in purchases:
            if not inward_supplies.get(supplier_gstin):
                continue

            summary_diff = {}
            if match_status == "Residual Match" and category != "CDNR":
                summary_diff = self.get_summary_difference(
                    purchases[supplier_gstin], inward_supplies[supplier_gstin]
                )

            for pur_name, pur in purchases[supplier_gstin].copy().items():
                if summary_diff and not (abs(summary_diff[pur.bill_date.month]) < 2):
                    continue

                for isup_name, isup in inward_supplies[supplier_gstin].copy().items():
                    if summary_diff and pur.bill_date.month != isup.bill_date.month:
                        continue

                    if not self.is_doc_matching(pur, isup, rules):
                        continue

                    self.update_matching_doc(match_status, pur.name, isup.name)

                    # Remove from current data to ensure matching is done only once.
                    purchases[supplier_gstin].pop(pur_name)
                    inward_supplies[supplier_gstin].pop(isup_name)
                    break

    def get_summary_difference(self, data1, data2):
        """
        Returns dict with difference of monthly purchase for given supplier data.
        Calculated only for Residual Match.

        Objective: Residual match is to match Invoices where bill no is completely different.
                    It should be matched for invoices of a given month only if difference in total invoice
                    value is negligible for purchase and inward supply.
        """
        summary = {}
        for doc in data1:
            summary.setdefault(doc.bill_date.month, 0)
            summary[doc.bill_date.month] += self.get_total_tax(doc)

        for doc in data2:
            summary.setdefault(doc.bill_date.month, 0)
            summary[doc.bill_date.month] -= self.get_total_tax(doc)

        return summary

    def is_doc_matching(self, pur, isup, rules):
        """
        Returns true if all fields match from purchase and inward supply as per rules.

        param pur: purchase doc
        param isup: inward supply doc
        param rules: list of rules to match as against FIELDS_TO_MATCH
        """

        for field in self.FIELDS_TO_MATCH:
            i = self.FIELDS_LIST.index(field)
            if not self.is_field_matching(pur, isup, field, rules[i]):
                return False

        return True

    def is_field_matching(self, pur, isup, field, rule):
        """
        Returns true if the field matches from purchase and inward supply as per the rule.

        param pur: purchase doc
        param isup: inward supply doc
        param field: field to match
        param rule: rule applied to match

        Rules:
            E: Exact Match
            F: Fuzzy Match
            N: Mismatch
          INT: Amount Difference <= INT

        """

        if rule == "E":
            return pur[field] == isup[field]
        elif rule == "N":
            return True
        elif rule == "F":
            return self.fuzzy_match(pur, isup)
        elif isinstance(rule, int):
            return self.get_amount_difference(pur, isup, field) <= rule

    def fuzzy_match(self, pur, isup):
        """
        Returns true if the (cleaned) bill_no approximately match.
        - For a fuzzy match, month of invoice and inward supply should be same.
        - First check for partial ratio, with 100% confidence
        - Next check for approximate match, with 90% confidence
        """
        if abs(pur.bill_date - isup.bill_date).days > 10:
            return False

        partial_ratio = fuzz.partial_ratio(pur._bill_no, isup._bill_no)
        if float(partial_ratio) == 100:
            return True

        return float(process.extractOne(pur._bill_no, [isup._bill_no])[1]) >= 90.0

    def get_amount_difference(self, pur, isup, field):
        if field == "cess":
            self.update_cess_amount(pur)

        return abs(pur.get(field, 0) - isup.get(field, 0))

    def update_cess_amount(self, doc):
        doc.cess = doc.get("cess", 0) + doc.get("cess_non_advol", 0)

    def get_total_tax(self, doc, prefix=False):
        total_tax = 0

        for tax in GST_TAX_TYPES:
            tax = f"isup_{tax}" if prefix else tax
            total_tax += doc.get(tax, 0)

        return total_tax

    def update_matching_doc(self, match_status, pur_name, isup_name):
        """Update matching doc for records."""

        if match_status == "Residual Match":
            match_status = "Mismatch"

        isup_fields = {
            "match_status": match_status,
            "link_doctype": "Purchase Invoice",
            "link_name": pur_name,
        }

        frappe.db.set_value("GST Inward Supply", isup_name, isup_fields)

    def get_purchase(self, category):
        gst_category = (
            ("Registered Regular", "Tax Deductor")
            if category in ("B2B", "CDNR", "ISD")
            else ("SEZ", "Overseas", "UIN Holders")
        )
        is_return = 1 if category == "CDNR" else 0

        query = (
            self.query_purchase_invoice(is_return=is_return)
            .where(
                self.PI.posting_date[self.purchase_from_date : self.purchase_to_date]
            )
            .where(self.PI.name.notin(self.query_matched_purchase_invoice()))
            .where(self.PI.ignore_reconciliation == 0)
            .where(self.PI.gst_category.isin(gst_category))
            .where(self.PI.is_return == is_return)
        )

        data = query.run(as_dict=True)

        for doc in data:
            doc.fy = self.get_fy(doc.bill_date or doc.posting_date)
            doc._bill_no = self.get_cleaner_bill_no(doc.bill_no, doc.fy)

        return self.get_dict_for_key("supplier_gstin", data)

    def query_purchase_invoice(self, additional_fields=None, is_return=False):
        gst_accounts = get_gst_accounts_by_type(self.company, "Input")
        tax_fields = [
            self.query_tax_amount(account).as_(tax[:-8])
            for tax, account in gst_accounts.items()
            if account
        ]

        fields = [
            "name",
            "supplier_gstin",
            "bill_no",
            "place_of_supply",
            "is_reverse_charge",
        ]

        if is_return:
            # return is initiated by the customer. So bill date may not be available or known.
            fields += [self.PI.posting_date.as_("bill_date")]
        else:
            fields += ["bill_date"]

        if additional_fields:
            fields += additional_fields

        pi_item = (
            frappe.qb.from_(self.PI_ITEM)
            .select(
                Abs(Sum(self.PI_ITEM.taxable_value)).as_("taxable_value"),
                self.PI_ITEM.parent,
            )
            .groupby(self.PI_ITEM.parent)
        )

        return (
            frappe.qb.from_(self.PI)
            .left_join(self.PI_TAX)
            .on(self.PI_TAX.parent == self.PI.name)
            .left_join(pi_item)
            .on(pi_item.parent == self.PI.name)
            .where(self.company_gstin == self.PI.company_gstin)
            .where(self.PI.docstatus == 1)
            # Filter for B2B transactions where match can be made
            .where(self.PI.supplier_gstin != "")
            .where(self.PI.gst_category != "Registered Composition")
            .where(self.PI.supplier_gstin.isnotnull())
            .groupby(self.PI.name)
            .select(*tax_fields, *fields, pi_item.taxable_value)
        )

    def query_matched_purchase_invoice(self):
        return (
            frappe.qb.from_(self.GSTR2)
            .select("link_name")
            .where(self.GSTR2.link_doctype == "Purchase Invoice")
        )

    def query_tax_amount(self, account):
        return Abs(
            Sum(
                Case()
                .when(
                    self.PI_TAX.account_head == account,
                    self.PI_TAX.base_tax_amount_after_discount_amount,
                )
                .else_(0)
            )
        )

    def get_inward_supply(self, category, amended_category):
        categories = [category, amended_category or None]
        query = self.query_inward_supply()
        data = (
            query.where(
                (self.GSTR2.match_status == "") | (self.GSTR2.match_status.isnull())
            )
            .where(self.GSTR2.action != "Ignore")
            .where(self.GSTR2.classification.isin(categories))
            .run(as_dict=True)
        )

        for doc in data:
            doc.fy = self.get_fy(doc.bill_date)
            doc._bill_no = self.get_cleaner_bill_no(doc.bill_no, doc.fy)

        return self.get_dict_for_key("supplier_gstin", data)

    def query_inward_supply(
        self, additional_fields=None, for_summary=False, filter_period=True
    ):
        fields = self.get_inward_supply_fields(additional_fields, for_summary)
        isup_periods = _get_periods(
            self.inward_supply_from_date, self.inward_supply_to_date
        )

        query = (
            frappe.qb.from_(self.GSTR2)
            .left_join(self.GSTR2_ITEM)
            .on(self.GSTR2_ITEM.parent == self.GSTR2.name)
            .where(self.company_gstin == self.GSTR2.company_gstin)
            .where(self.GSTR2.match_status != "Amended")
            .groupby(self.GSTR2_ITEM.parent)
            .select(*fields)
        )

        if not filter_period:
            return query

        if self.gst_return == "GSTR 2B":
            query = query.where((self.GSTR2.return_period_2b.isin(isup_periods)))
        else:
            query = query.where(
                (self.GSTR2.return_period_2b.isin(isup_periods))
                | (self.GSTR2.sup_return_period.isin(isup_periods))
                | (self.GSTR2.other_return_period.isin(isup_periods))
            )

        return query

    def get_inward_supply_fields(
        self, additional_fields=None, for_summary=False, table=None
    ):
        """
        Returns fields for inward supply query.

        Column name should be different where we join this query with purchase query.
        Returns column names with 'isup_' prefix for summary where different table is provided.
        """
        if not table:
            table = self.GSTR2

        fields = [
            "bill_no",
            "bill_date",
            "name",
            "supplier_gstin",
            "is_reverse_charge",
            "place_of_supply",
        ]

        if additional_fields:
            fields += additional_fields

        fields = [
            table[field].as_(f"isup_{field}" if for_summary else field)
            for field in fields
        ]

        tax_fields = self.get_tax_fields_for_inward_supply(table, for_summary)

        return [*fields, *tax_fields]

    def get_tax_fields_for_inward_supply(self, table, for_summary):
        """
        Returns tax fields for inward supply query.
        Where query is used as subquery, fields are fetch from table (subquery) instead of item table.
        """
        fields = GST_TAX_TYPES[:-1] + ("taxable_value",)
        if table == self.GSTR2:
            tax_fields = [
                Sum(self.GSTR2_ITEM[field]).as_(
                    f"isup_{field}" if for_summary else field
                )
                for field in fields
            ]
        else:
            tax_fields = [table[field].as_(f"isup_{field}") for field in fields]

        return tax_fields

    def get_pan_level_data(self, data):
        out = {}
        for gstin, invoices in data.items():
            pan = gstin[2:-3]
            out.setdefault(pan, {})
            out[pan].update(invoices)

        return out

    def get_fy(self, date):
        if not date:
            return

        # Standard for India. Presuming 99.99% suppliers would use this.
        if date.month < 4:
            return f"{date.year - 1}-{date.year}"

        return f"{date.year}-{date.year + 1}"

    def get_cleaner_bill_no(self, bill_no, fy):
        """
        - Attempts to return bill number without financial year.
        - Removes trailing zeros from bill number.
        """

        fy = fy.split("-")
        replace_list = [
            f"{fy[0]}-{fy[1]}",
            f"{fy[0]}/{fy[1]}",
            f"{fy[0]}-{fy[1][2:]}",
            f"{fy[0]}/{fy[1][2:]}",
            f"{fy[0][2:]}-{fy[1][2:]}",
            f"{fy[0][2:]}/{fy[1][2:]}",
            "/",  # these are only special characters allowed in invoice
            "-",
        ]

        inv = bill_no
        for replace in replace_list:
            inv = inv.replace(replace, " ")
        inv = " ".join(inv.split()).lstrip("0")
        return inv

    def get_dict_for_key(self, key, list):
        new_dict = frappe._dict()
        for data in list:
            new_dict.setdefault(data[key], {})[data.name] = data

        return new_dict

    @frappe.whitelist()
    def upload_gstr(self, return_type, period, file_path):
        return_type = ReturnType(return_type)
        json_data = get_json_from_file(file_path)
        if return_type == ReturnType.GSTR2A:
            return save_gstr_2a(self.company_gstin, period, json_data)

        if return_type == ReturnType.GSTR2B:
            return save_gstr_2b(self.company_gstin, period, json_data)

    @frappe.whitelist()
    def download_gstr_2a(self, fiscal_year, force=False, otp=None):
        return_type = ReturnType.GSTR2A
        periods = get_periods(fiscal_year, return_type)
        if not force:
            periods = self.get_periods_to_download(return_type, periods)

        return download_gstr_2a(self.company_gstin, periods, otp)

    @frappe.whitelist()
    def download_gstr_2b(self, fiscal_year, otp=None):
        return_type = ReturnType.GSTR2B
        periods = self.get_periods_to_download(
            return_type, get_periods(fiscal_year, return_type)
        )
        return download_gstr_2b(self.company_gstin, periods, otp)

    def get_periods_to_download(self, return_type, periods):
        existing_periods = get_import_history(
            self.company_gstin,
            return_type,
            periods,
            pluck="return_period",
        )

        return [period for period in periods if period not in existing_periods]

    @frappe.whitelist()
    def get_import_history(self, return_type, fiscal_year, for_download=True):
        # TODO: refactor this method
        if not return_type:
            return

        return_type = ReturnType(return_type)
        periods = get_periods(fiscal_year, return_type, True)
        history = get_import_history(self.company_gstin, return_type, periods)

        columns = [
            "Period",
            "Classification",
            "Status",
            f"{'Downloaded' if for_download else 'Uploaded'} On",
        ]

        settings = frappe.get_cached_doc("GST Settings")

        data = {}
        for period in periods:
            # TODO: skip if today is not greater than 14th return period's next months
            data[period] = []
            status = "🟢 &nbsp; Downloaded"
            for category in GSTRCategory:
                if category.value == "ISDA" and return_type == ReturnType.GSTR2A:
                    continue

                if not settings.enable_overseas_transactions and category.value in (
                    "IMPG",
                    "IMPGSEZ",
                ):
                    continue

                download = next(
                    (
                        log
                        for log in history
                        if log.return_period == period
                        and log.classification in (category.value, "")
                    ),
                    None,
                )

                status = "🟠 &nbsp; Not Downloaded"
                if download:
                    status = "🟢 &nbsp; Downloaded"
                    if download.data_not_found:
                        status = "🔵 &nbsp; Data Not Found"
                    if download.request_id:
                        status = "🔵 &nbsp; Queued"

                if not for_download:
                    status = status.replace("Downloaded", "Uploaded")

                _dict = {
                    "Classification": category.value
                    if return_type is ReturnType.GSTR2A
                    else "ALL",
                    "Status": status,
                    columns[-1]: "✅ &nbsp;"
                    + download.last_updated_on.strftime("%d-%m-%Y %H:%M:%S")
                    if download
                    else "",
                }
                if _dict not in data[period]:
                    data[period].append(_dict)

        return frappe.render_template(
            "gst_india/doctype/purchase_reconciliation_tool/download_history.html",
            {"columns": columns, "data": data},
        )

    @frappe.whitelist()
    def get_return_period_from_file(self, return_type, file_path):
        if not file_path:
            return

        return_type = ReturnType(return_type)
        try:
            json_data = get_json_from_file(file_path)
            if return_type == ReturnType.GSTR2A:
                return json_data.get("fp")

            if return_type == ReturnType.GSTR2B:
                return json_data.get("data").get("rtnprd")

        except Exception:
            pass

    @frappe.whitelist()
    def get_date_range(self, period):
        today = getdate()
        start_month = end_month = month = today.month
        start_year = end_year = year = today.year
        quarter = ceil(month / 3)

        if "Previous Month" in period:
            start_month = end_month = month - 1 or 12
        elif "Quarter" in period:
            end_month = quarter * 3
            if "Previous" in period:
                end_month = (quarter - 1) * 3 or 12
            start_month = end_month - 2

        if start_month > month:
            start_year = end_year = year - 1
        elif "Year" in period:
            start_month = 4
            end_month = 3
            if "Previous" in period:
                start_year = end_year = year - 1
            if start_month > month:
                start_year -= 1
            else:
                end_year += 1

        date1 = _get_first_day(start_month, start_year)
        date2 = _get_last_day(end_month, end_year)
        date2 = date2 if date2 < today else today
        return [date1, date2]

    def get_reconciliation_data(self, purchase_names=None, inward_supply_names=None):
        """
        Get Reconciliation data based on standard filters
        Returns
            - Inward Supply: for the return month as per 2A and 2B
            - Purchase Invoice: All invoices matching with inward supply (irrespective of purchase period choosen)
                Unmatched Purchase Invoice for the period choosen

        params:
            - purchase_names: list of purchase invoice names (Optional)
            - inward_supply_names: list of inward supply names (Optional)
        """
        purchase = self.query_purchase_invoice(
            additional_fields=[
                "supplier",
                "supplier_name",
                "is_return",
                "gst_category",
                "ignore_reconciliation",
            ]
        )
        isup_additional_fields = [
            "supplier_name",
            "classification",
            "match_status",
            "action",
        ]
        inward_supply = self.query_inward_supply(
            isup_additional_fields + ["link_doctype", "link_name"]
        )

        # get selective data for manually linked invoices
        if inward_supply_names:
            inward_supply = inward_supply.where(
                self.GSTR2.name.isin(inward_supply_names)
            )
            purchase = purchase.where(self.PI.name.isin(purchase_names))

        # this will not return missing in inward supply (if any)
        reconciliation_data = (
            purchase.join(inward_supply)
            .on(
                (inward_supply.link_doctype == "Purchase Invoice")
                & (inward_supply.link_name == self.PI.name)
            )
            .select(
                *self.get_inward_supply_fields(
                    isup_additional_fields,
                    for_summary=True,
                    table=inward_supply,
                )
            )
            .run(as_dict=True)
        )

        # add missing in inward supply
        reconciliation_data = reconciliation_data + (
            purchase.where(
                self.PI.posting_date[self.purchase_from_date : self.purchase_to_date]
            )
            .where(self.PI.name.notin(self.query_matched_purchase_invoice()))
            .run(as_dict=True)
        )

        # add missing in purchase invoice
        missing_in_pr = self.query_inward_supply(
            isup_additional_fields, for_summary=True
        ).where((self.GSTR2.link_name == "") | (self.GSTR2.link_name.isnull()))

        if inward_supply_names:
            missing_in_pr = missing_in_pr.where(
                self.GSTR2.name.isin(inward_supply_names)
            )

        reconciliation_data = reconciliation_data + missing_in_pr.run(as_dict=True)

        self.process_reconciliation_data(reconciliation_data)
        return {
            "data": reconciliation_data,
        }

    def process_reconciliation_data(self, reconciliation_data):
        fields_to_update = [
            "supplier_name",
            "supplier_gstin",
            "place_of_supply",
            "is_reverse_charge",
            "bill_no",
            "bill_date",
        ]

        def _update_doc(doc, differences):
            # update differences
            doc.differences = ", ".join(differences)

            # update pan
            doc.pan = doc.supplier_gstin[2:-3]

            # remove columns
            columns_to_remove = [
                "isup_supplier_name",
                "ignore_reconciliation",
                "gst_category",
                "is_return",
            ]
            if isinstance(columns_to_remove, str):
                columns_to_remove = (columns_to_remove,)

            for column in columns_to_remove:
                doc.pop(column, None)

        # modify doc
        for doc in reconciliation_data:
            differences = []

            # update amount differences
            doc.taxable_value_diff = rounded(
                doc.get("isup_taxable_value", 0) - doc.get("taxable_value", 0), 2
            )
            doc.tax_diff = rounded(
                self.get_total_tax(doc, True) - self.get_total_tax(doc), 2
            )
            self.update_cess_amount(doc)

            # update missing values
            if not doc.name:
                doc.isup_match_status = "Missing in PR"
                for field in fields_to_update:
                    doc[field] = doc.get(f"isup_{field}", "")

                if not doc.supplier_name:
                    doc.supplier_name = self.guess_supplier_name(doc.supplier_gstin)

                _update_doc(doc, differences)
                continue

            if not doc.isup_name:
                doc.isup_match_status = "Missing in 2A/2B"
                doc.isup_action = (
                    "Ignore"
                    if doc.get("ignore_reconciliation", 0) == 1
                    else "No Action"
                )

                classification = self.guess_classification(doc)

                doc.isup_classification = classification
                _update_doc(doc, differences)
                continue

            if doc.isup_match_status not in ("Mismatch", "Manual Match"):
                if abs(doc.tax_diff) > 0.01 or abs(doc.taxable_value_diff) > 0.01:
                    differences.append("Rounding Difference")

                _update_doc(doc, differences)
                continue

            # update differences
            for field in self.FIELDS_TO_MATCH:
                if field == "bill_no":
                    continue

                isup_value = doc.get(f"isup_{field}")

                if isup_value != doc.get(field):
                    label = self.FIELDS_TO_MATCH[field]
                    differences.append(label)

            _update_doc(doc, differences)

    def guess_classification(self, doc):
        classification = self.GST_CATEGORIES.get(doc.gst_category)
        if doc.is_return and classification == "B2B":
            classification = "CDNR"
        return classification

    def guess_supplier_name(self, gstin):
        if party := self.gstin_party_map.get(gstin):
            return party

        return self.gstin_party_map.setdefault(
            gstin, get_party_for_gstin(gstin) or "Unknown"
        )

    @frappe.whitelist()
    def link_documents(self, pur_name, isup_name):
        if not pur_name or not isup_name:
            return

        purchases = []
        inward_supplies = []

        # silently handle existing links
        if isup_linked_with := frappe.db.get_value(
            "GST Inward Supply", isup_name, "link_name"
        ):
            self._unlink_documents((isup_name,))
            purchases.append(isup_linked_with)

        if (
            pur_linked_with := frappe.qb.from_(self.GSTR2)
            .select("name")
            .where(self.GSTR2.link_doctype == "Purchase Invoice")
            .where(self.GSTR2.link_name == pur_name)
            .run()
        ):
            self._unlink_documents((pur_linked_with,))
            inward_supplies.append(pur_linked_with)

        # link documents
        frappe.db.set_value(
            "GST Inward Supply",
            isup_name,
            {
                "link_doctype": "Purchase Invoice",
                "link_name": pur_name,
                "match_status": "Manual Match",
            },
        )
        purchases.append(pur_name)
        inward_supplies.append(isup_name)

        # get updated data
        return self.get_reconciliation_data(purchases, inward_supplies).get("data")

    @frappe.whitelist()
    def unlink_documents(self, data):
        if isinstance(data, str):
            data = frappe.parse_json(data)

        isup_docs = []
        isup_actions = []
        for doc in data:
            isup_docs.append(doc.get("isup_name"))
            if doc.get("isup_action") not in ("Ignore", "Pending"):
                isup_actions.append(doc.get("isup_name"))

        self._unlink_documents(isup_docs, isup_actions)

    def _unlink_documents(self, isup_docs, isup_actions=None):
        if isup_docs:
            (
                frappe.qb.update(self.GSTR2)
                .set("link_doctype", "")
                .set("link_name", "")
                .set("match_status", "Unlinked")
                .where(self.GSTR2.name.isin(isup_docs))
                .run()
            )

        if isup_actions:
            (
                frappe.qb.update(self.GSTR2)
                .set("action", "No Action")
                .where(self.GSTR2.name.isin(isup_actions))
                .run()
            )

    @frappe.whitelist()
    def apply_action(self, data, action):
        if isinstance(data, str):
            data = frappe.parse_json(data)

        is_ignore_action = action == "Ignore"

        isup_docs = []
        pur_docs = []

        for doc in data:
            isup_docs.append(doc.get("isup_name"))

            if is_ignore_action and not doc.get("isup_name"):
                pur_docs.append(doc.get("name"))

        if isup_docs:
            (
                frappe.qb.update(self.GSTR2)
                .set("action", action)
                .where(self.GSTR2.name.isin(isup_docs))
                .run()
            )

        if pur_docs:
            (
                frappe.qb.update(self.PI)
                .set("ignore_reconciliation", 1)
                .where(self.PI.name.isin(pur_docs))
                .run()
            )

    @frappe.whitelist()
    def get_link_options(self, doctype, filters):
        if isinstance(filters, dict):
            filters = frappe._dict(filters)

        if doctype == "Purchase Invoice":
            query = self.query_purchase_invoice(["gst_category", "is_return"])
            table = self.PI
        elif doctype == "GST Inward Supply":
            query = self.query_inward_supply(
                ["classification"], for_summary=True, filter_period=False
            )
            table = self.GSTR2

        query = query.where(
            table.supplier_gstin.like(f"%{filters.supplier_gstin}%")
        ).where(table.bill_date[filters.bill_from_date : filters.bill_to_date])

        if not filters.show_matched:
            if doctype == "GST Inward Supply":
                query = query.where(
                    (table.link_name == "") | (table.link_name.isnull())
                )

            else:
                query = query.where(
                    table.name.notin(self.query_matched_purchase_invoice())
                )

        data = self._get_link_options(query.run(as_dict=True), doctype)
        return data

    def _get_link_options(self, data, doctype):
        prefix = "isup_" if doctype == "GST Inward Supply" else ""

        for row in data:
            row.value = row.label = row[prefix + "name"]
            if not row.get("isup_classification"):
                row.isup_classification = self.guess_classification(row)

            row.description = f"{row[prefix + 'bill_no']}, {row[prefix + 'bill_date']}, Taxable Amount: {row[prefix + 'taxable_value']}"
            row.description += f", Tax Amount: {self.get_total_tax(row, prefix)}, {row['isup_classification']}"

        return data


def get_periods(fiscal_year, return_type: ReturnType, reversed=False):
    """Returns a list of month (formatted as `MMYYYY`) in a fiscal year"""

    fiscal_year = frappe.db.get_value(
        "Fiscal Year",
        fiscal_year,
        ("year_start_date as start_date", "year_end_date as end_date"),
        as_dict=True,
    )

    if not fiscal_year:
        return []

    end_date = min(fiscal_year.end_date, _getdate(return_type))

    # latest to oldest
    return tuple(_reversed(_get_periods(fiscal_year.start_date, end_date), reversed))


def _get_periods(start_date, end_date):
    """Returns a list of month (formatted as `MMYYYY`) in given date range"""

    if isinstance(start_date, str):
        start_date = getdate(start_date)

    if isinstance(end_date, str):
        end_date = getdate(end_date)

    return [
        dt.strftime("%m%Y") for dt in rrule(MONTHLY, dtstart=start_date, until=end_date)
    ]


def _reversed(lst, reverse):
    if reverse:
        return reversed(lst)
    return lst


def _getdate(return_type):
    if return_type == ReturnType.GSTR2B:
        if getdate().day >= GSTR2B_GEN_DATE:
            return add_months(getdate(), -1)
        else:
            return add_months(getdate(), -2)

    return getdate()


def _get_first_day(month, year):
    """Returns first day of the month"""
    return date(year, month, 1)


def _get_last_day(month, year):
    """Returns last day of the month"""
    return date(year, month, monthrange(year, month)[1])


def get_import_history(
    company_gstin, return_type: ReturnType, periods: List[str], fields=None, pluck=None
):
    if not (fields or pluck):
        fields = (
            "return_period",
            "classification",
            "data_not_found",
            "last_updated_on",
            "request_id",
        )

    return frappe.db.get_all(
        "GSTR Import Log",
        filters={
            "gstin": company_gstin,
            "return_type": return_type.value,
            "return_period": ("in", periods),
        },
        fields=fields,
        pluck=pluck,
    )


@frappe.whitelist()
def generate_excel_attachment(data, doc):
    build_data = BuildExcel(doc, data, is_supplier_specific=True, email=True)

    xlsx_file, filename = build_data.export_data()
    xlsx_data = xlsx_file.getvalue()

    # Upload attachment for email xlsx data using communication make() method
    folder = frappe.form_dict.folder or "Home"
    file_url = frappe.form_dict.file_url or ""

    file = frappe.get_doc(
        {
            "doctype": "File",
            "attached_to_doctype": "Purchase Reconciliation Tool",
            "folder": folder,
            "file_name": f"{filename}.xlsx",
            "file_url": file_url,
            "is_private": 0,
            "content": xlsx_data,
        }
    )
    file.save(ignore_permissions=True)
    return [file]


@frappe.whitelist()
def download_excel_report(data, doc, is_supplier_specific=False):
    build_data = BuildExcel(doc, data, is_supplier_specific)
    build_data.export_data()


def parse_params(fun):
    def wrapper(*args, **kwargs):
        args = [frappe.parse_json(arg) for arg in args]
        kwargs = {k: frappe.parse_json(v) for k, v in kwargs.items()}
        return fun(*args, **kwargs)

    return wrapper


class BuildExcel:
    COLOR_PALLATE = frappe._dict(
        {
            "dark_gray": "d9d9d9",
            "light_gray": "f2f2f2",
            "dark_pink": "e6b9b8",
            "light_pink": "f2dcdb",
            "sky_blue": "c6d9f1",
            "light_blue": "dce6f2",
            "green": "d7e4bd",
            "light_green": "ebf1de",
        }
    )

    @parse_params
    def __init__(self, doc, data, is_supplier_specific=False, email=False):
        """
        :param doc: purchase reconciliation tool doc
        :param data: data to be exported
        :param is_supplier_specific: if true, data will be downloded for specific supplier
        :param email: send the file as email
        """
        self.doc = doc
        self.data = data
        self.is_supplier_specific = is_supplier_specific
        self.email = email
        self.set_headers()
        self.set_filters()

    def export_data(self):
        """Exports data to an excel file"""
        excel = ExcelExporter()
        excel.create_sheet(
            sheet_name="Match Summary Data",
            filters=self.filters,
            headers=self.match_summary_header,
            data=self.get_match_summary_data(),
        )

        if not self.is_supplier_specific:
            excel.create_sheet(
                sheet_name="Supplier Data",
                filters=self.filters,
                headers=self.supplier_header,
                data=self.get_supplier_data(),
            )

        excel.create_sheet(
            sheet_name="Invoice Data",
            filters=self.filters,
            merged_headers=self.get_merge_headers(),
            headers=self.invoice_header,
            data=self.get_invoice_data(),
        )

        excel.remove_sheet("Sheet")

        file_name = self.get_file_name()
        if self.email:
            xlsx_data = excel.save_workbook()
            return [xlsx_data, file_name]

        excel.export(file_name)

    def set_headers(self):
        """Sets headers for the excel file"""

        self.match_summary_header = self.get_match_summary_columns()
        self.supplier_header = self.get_supplier_columns()
        self.invoice_header = self.get_invoice_columns()

    def set_filters(self):
        """Add filters to the sheet"""

        label = "2B" if self.doc.gst_return == "GSTR 2B" else "2A/2B"
        self.period = (
            f"{self.doc.inward_supply_from_date} to {self.doc.inward_supply_to_date}"
        )

        self.filters = frappe._dict(
            {
                "Company Name": self.doc.company,
                "GSTIN": self.doc.company_gstin,
                f"Return Period ({label})": self.period,
            }
        )

    def get_merge_headers(self):
        """Returns merged_headers for the excel file"""
        return frappe._dict(
            {
                "2A / 2B": ["isup_bill_no", "isup_cess"],
                "Purchase Data": ["bill_no", "cess"],
            }
        )

    def get_match_summary_data(self):
        return self.process_data(
            self.data.get("match_summary"),
            self.match_summary_header,
        )

    def get_supplier_data(self):
        return self.process_data(
            self.data.get("supplier_summary"), self.supplier_header
        )

    def get_invoice_data(self):
        return self.process_data(self.data.get("invoice_summary"), self.invoice_header)

    def process_data(self, data, column_list):
        """return required list of dict for the excel file"""
        if not data:
            return

        out = []
        fields = [d.get("fieldname") for d in column_list]
        purchase_fields = [field.get("fieldname") for field in self.pr_columns]
        for row in data:
            new_row = {}
            for field in fields:
                if field not in row:
                    row[field] = None

                # pur data in row (for invoice_summary) is polluted for Missing in PR
                if field in purchase_fields and not row.get("name"):
                    row[field] = None

                self.assign_value(field, row, new_row)

            out.append(new_row)

        return out

    def assign_value(self, field, source_data, target_data):
        if source_data.get(field) is None:
            target_data[field] = None
            return

        if "is_reverse_charge" in field:
            target_data[field] = "Yes" if source_data.get(field) else "No"
            return

        target_data[field] = source_data.get(field)

    def get_file_name(self):
        """Returns file name for the excel file"""
        if not self.is_supplier_specific:
            return f"{self.doc.company_gstin}_{self.period}_report"

        invoice = self.data.get("invoice_summary")[0]
        file_name = f"{invoice.get('supplier_name')}_{invoice.get('supplier_gstin')}"
        return file_name.replace(" ", "_")

    def get_match_summary_columns(self):
        """
        Defaults:
            - bg_color: self.COLOR_PALLATE.dark_gray
            - bg_color_data": self.COLOR_PALLATE.light_gray
            - bold: 1
            - align_header: "center"
            - align_data: "general"
            - width: 20
        """
        return [
            {
                "label": "Match Status",
                "fieldname": "isup_match_status",
                "data_format": {"horizontal": "left"},
                "header_format": {"horizontal": "center"},
            },
            {
                "label": "Count \n 2A/2B Docs",
                "fieldname": "count_isup_docs",
                "fieldtype": "Int",
                "data_format": {"number_format": "#,##0"},
            },
            {
                "label": "Count \n Purchase Docs",
                "fieldname": "count_pur_docs",
                "fieldtype": "Int",
                "data_format": {"number_format": "#,##0"},
            },
            {
                "label": "Taxable Amount Diff \n 2A/2B - Purchase",
                "fieldname": "taxable_value_diff",
                "fieldtype": "Float",
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_pink,
                    "number_format": "0.00",
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.dark_pink,
                },
            },
            {
                "label": "Tax Difference \n 2A/2B - Purchase",
                "fieldname": "tax_diff",
                "fieldtype": "Float",
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_pink,
                    "number_format": "0.00",
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.dark_pink,
                },
            },
            {
                "label": "%Action Taken",
                "fieldname": "count_action_taken",
                "data_format": {"number_format": "0.00%"},
                "width": 12,
            },
        ]

    def get_supplier_columns(self):
        return [
            {
                "label": "Supplier Name",
                "fieldname": "supplier_name",
                "data_format": {"horizontal": "left"},
            },
            {
                "label": "Supplier GSTIN",
                "fieldname": "supplier_gstin",
                "data_format": {"horizontal": "left"},
            },
            {
                "label": "Count \n 2A/2B Docs",
                "fieldname": "count_isup_docs",
                "fieldtype": "Int",
                "data_format": {"number_format": "#,##0"},
            },
            {
                "label": "Count \n Purchase Docs",
                "fieldname": "count_pur_docs",
                "fieldtype": "Int",
                "data_format": {
                    "number_format": "#,##0",
                },
            },
            {
                "label": "Taxable Amount Diff \n 2A/2B - Purchase",
                "fieldname": "taxable_value_diff",
                "fieldtype": "Float",
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_pink,
                    "number_format": "0.00",
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.dark_pink,
                },
            },
            {
                "label": "Tax Difference \n 2A/2B - Purchase",
                "fieldname": "tax_diff",
                "fieldtype": "Float",
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_pink,
                    "number_format": "0.00",
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.dark_pink,
                },
            },
            {
                "label": "%Action Taken",
                "fieldname": "count_action_taken",
                "data_format": {"number_format": "0.00%"},
                "header_format": {
                    "width": 12,
                },
            },
        ]

    def get_invoice_columns(self):
        self.pr_columns = [
            {
                "label": "Bill No",
                "fieldname": "bill_no",
                "compare_with": "isup_bill_no",
                "data_format": {
                    "horizontal": "left",
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": 12,
                },
            },
            {
                "label": "Bill Date",
                "fieldname": "bill_date",
                "compare_with": "isup_bill_date",
                "data_format": {
                    "horizontal": "left",
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": 12,
                },
            },
            {
                "label": "GSTIN",
                "fieldname": "supplier_gstin",
                "compare_with": "isup_supplier_gstin",
                "data_format": {
                    "horizontal": "left",
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": 15,
                },
            },
            {
                "label": "Place of Supply",
                "fieldname": "place_of_supply",
                "compare_with": "isup_place_of_supply",
                "data_format": {
                    "horizontal": "left",
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": 12,
                },
            },
            {
                "label": "Reverse Charge",
                "fieldname": "is_reverse_charge",
                "compare_with": "isup_is_reverse_charge",
                "data_format": {
                    "horizontal": "left",
                    "bg_color": self.COLOR_PALLATE.light_green,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": 12,
                },
            },
            {
                "label": "Taxable Value",
                "fieldname": "taxable_value",
                "compare_with": "isup_taxable_value",
                "fieldtype": "Float",
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": "0.00",
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": 12,
                },
            },
            {
                "label": "CGST",
                "fieldname": "cgst",
                "compare_with": "isup_cgst",
                "fieldtype": "Float",
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": "0.00",
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": 12,
                },
            },
            {
                "label": "SGST",
                "fieldname": "sgst",
                "compare_with": "isup_sgst",
                "fieldtype": "Float",
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": "0.00",
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": 12,
                },
            },
            {
                "label": "IGST",
                "fieldname": "igst",
                "compare_with": "isup_igst",
                "fieldtype": "Float",
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": "0.00",
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": 12,
                },
            },
            {
                "label": "CESS",
                "fieldname": "cess",
                "compare_with": "isup_cess",
                "fieldtype": "Float",
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_green,
                    "number_format": "0.00",
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.green,
                    "width": 12,
                },
            },
        ]
        self.isup_columns = [
            {
                "label": "Bill No",
                "fieldname": "isup_bill_no",
                "compare_with": "bill_no",
                "data_format": {
                    "horizontal": "left",
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                    "width": 12,
                },
            },
            {
                "label": "Bill Date",
                "fieldname": "isup_bill_date",
                "compare_with": "bill_date",
                "data_format": {
                    "horizontal": "left",
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                    "width": 12,
                },
            },
            {
                "label": "GSTIN",
                "fieldname": "isup_supplier_gstin",
                "compare_with": "supplier_gstin",
                "data_format": {
                    "horizontal": "left",
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                    "width": 15,
                },
            },
            {
                "label": "Place of Supply",
                "fieldname": "isup_place_of_supply",
                "compare_with": "place_of_supply",
                "data_format": {
                    "horizontal": "left",
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                    "width": 12,
                },
            },
            {
                "label": "Reverse Charge",
                "fieldname": "isup_is_reverse_charge",
                "compare_with": "is_reverse_charge",
                "data_format": {
                    "horizontal": "left",
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                    "width": 12,
                },
            },
            {
                "label": "Taxable Value",
                "fieldname": "isup_taxable_value",
                "compare_with": "taxable_value",
                "fieldtype": "Float",
                "data_format": {
                    "number_format": "0.00",
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                    "width": 12,
                },
            },
            {
                "label": "CGST",
                "fieldname": "isup_cgst",
                "compare_with": "cgst",
                "fieldtype": "Float",
                "data_format": {
                    "number_format": "0.00",
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                    "width": 12,
                },
            },
            {
                "label": "SGST",
                "fieldname": "isup_sgst",
                "compare_with": "sgst",
                "fieldtype": "Float",
                "data_format": {
                    "number_format": "0.00",
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                    "width": 12,
                },
            },
            {
                "label": "IGST",
                "fieldname": "isup_igst",
                "compare_with": "igst",
                "fieldtype": "Float",
                "data_format": {
                    "number_format": "0.00",
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                    "width": 12,
                },
            },
            {
                "label": "CESS",
                "fieldname": "isup_cess",
                "compare_with": "cess",
                "fieldtype": "Float",
                "data_format": {
                    "number_format": "0.00",
                    "bg_color": self.COLOR_PALLATE.light_blue,
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.sky_blue,
                    "width": 12,
                },
            },
        ]
        inv_columns = [
            {
                "label": "Action Status",
                "fieldname": "isup_action",
                "data_format": {"horizontal": "left"},
            },
            {
                "label": "Match Status",
                "fieldname": "isup_match_status",
                "data_format": {"horizontal": "left"},
            },
            {
                "label": "Supplier Name",
                "fieldname": "supplier_name",
                "data_format": {"horizontal": "left"},
            },
            {
                "label": "PAN",
                "fieldname": "pan",
                "data_format": {"horizontal": "center"},
                "header_format": {
                    "width": 15,
                },
            },
            {
                "label": "Classification",
                "fieldname": "isup_classification",
                "data_format": {"horizontal": "left"},
                "header_format": {
                    "width": 11,
                },
            },
            {
                "label": "Taxable Value Difference",
                "fieldname": "taxable_value_diff",
                "fieldtype": "Float",
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_pink,
                    "number_format": "0.00",
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.dark_pink,
                    "width": 12,
                },
            },
            {
                "label": "Tax Difference",
                "fieldname": "tax_diff",
                "fieldtype": "Float",
                "data_format": {
                    "bg_color": self.COLOR_PALLATE.light_pink,
                    "number_format": "0.00",
                },
                "header_format": {
                    "bg_color": self.COLOR_PALLATE.dark_pink,
                    "width": 12,
                },
            },
        ]
        inv_columns.extend(self.isup_columns)
        inv_columns.extend(self.pr_columns)
        return inv_columns
