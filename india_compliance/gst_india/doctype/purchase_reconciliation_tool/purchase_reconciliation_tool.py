# Copyright (c) 2022, Resilient Tech and contributors
# For license information, please see license.txt

from calendar import monthrange
from datetime import datetime
from math import ceil
from typing import List

from dateutil.rrule import MONTHLY, rrule
from rapidfuzz import fuzz, process

import frappe
from frappe.model.document import Document
from frappe.query_builder import Case
from frappe.query_builder.functions import Abs, Sum
from frappe.utils import add_months, getdate

from india_compliance.gst_india.constants import GST_TAX_TYPES
from india_compliance.gst_india.utils import (
    get_gst_accounts_by_type,
    get_json_from_file,
)
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
    FIELDS_TO_MATCH = [
        "fy",
        "bill_no",
        "place_of_supply",
        "is_reverse_charge",
        "cgst",
        "sgst",
        "igst",
        "cess",
        "document_value",
    ]
    RULES = [
        {"Exact Match": ["E", "E", "E", "E", 0, 0, 0, 0, 0]},
        {"Suggested Match": ["E", "F", "E", "E", 0, 0, 0, 0, 0]},
        {"Suggested Match": ["E", "E", "E", "E", 1, 1, 1, 1, 2]},
        {"Suggested Match": ["E", "F", "E", "E", 1, 1, 1, 1, 2]},
        {"Mismatch": ["E", "E", "N", "N", "N", "N", "N", "N", "N"]},
        {"Mismatch": ["E", "F", "N", "N", "N", "N", "N", "N", "N"]},
        {"Residual Match": ["E", "N", "E", "E", 1, 1, 1, 1, 2]},
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
        self.gstr2 = frappe.qb.DocType("Inward Supply")
        self.gstr2_item = frappe.qb.DocType("Inward Supply Item")
        self.pi = frappe.qb.DocType("Purchase Invoice")
        self.pi_tax = frappe.qb.DocType("Purchase Taxes and Charges")

    def onload(self):
        if hasattr(self, "reconciliation_data"):
            self.set_onload("reconciliation_data", self.reconciliation_data)

    def validate(self):
        # set inward_supply_from_date to first day of the month
        date = getdate(self.inward_supply_from_date)
        self.inward_supply_from_date = _get_first_day(date.month, date.year)

    def on_update(self):
        # reconcile purchases and inward supplies
        for category, amended_category in (
            ("B2B", "B2BA"),
            ("CDNR", "CDNRA"),
            ("ISD", "ISDA"),
            ("IMPG", ""),
            ("IMPGSEZ", ""),
        ):
            self.reconcile(category, amended_category)

        self.reconciliation_data = self.get_reconciliation_data()

    def reconcile(self, category, amended_category):
        """
        Reconcile purchases and inward supplies for given category.
        """
        purchases = self.get_purchase(category)
        inward_supplies = self.get_inward_supply(category, amended_category)

        if not (purchases and inward_supplies):
            return

        for rule_map in self.RULES:
            for match_status, rules in rule_map.items():
                self._reconcile(purchases, inward_supplies, match_status, rules)

    def _reconcile(self, purchases, inward_supplies, match_status, rules):
        """
        Sequentially reconcile invoices as per rules list.
        - Reconciliation only done between invoices of same GSTIN.
        - Where a match is found, update Inward Supply and Purchase Invoice.
        """

        for supplier_gstin in purchases:
            if not inward_supplies.get(supplier_gstin):
                continue

            summary_diff = {}
            if match_status == "Residual Match":
                summary_diff = self.get_summary_difference(
                    purchases[supplier_gstin], inward_supplies[supplier_gstin]
                )

            for pur in purchases[supplier_gstin][:]:
                if summary_diff and not (abs(summary_diff[pur.bill_date.month]) < 2):
                    continue

                for isup in inward_supplies[supplier_gstin][:]:
                    if summary_diff and pur.bill_date.month != isup.bill_date.month:
                        continue

                    if not self.is_doc_matching(pur, isup, rules):
                        continue

                    self.update_matching_doc(match_status, pur.name, isup.name)

                    # Remove from current data to ensure matching is done only once.
                    purchases[supplier_gstin].remove(pur)
                    inward_supplies[supplier_gstin].remove(isup)
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
            i = self.FIELDS_TO_MATCH.index(field)
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

        frappe.db.set_value("Inward Supply", isup_name, isup_fields)
        frappe.db.set_value("Purchase Invoice", pur_name, "inward_supply", isup_name)

    def get_purchase(self, category):
        gst_category = (
            ("Registered Regular", "Tax Deductor")
            if category in ["B2B", "CDNR", "ISD"]
            else ("SEZ", "Overseas", "UIN Holders")
        )
        is_return = 1 if category == "CDNR" else 0

        query = (
            self.query_purchase_invoice(["name"])
            .where(
                self.pi.posting_date[self.purchase_from_date : self.purchase_to_date]
            )
            .where((self.pi.inward_supply == "") | (self.pi.inward_supply.isnull()))
            .where(self.pi.ignore_reconciliation == 0)
            .where(self.pi.gst_category.isin(gst_category))
            .where(self.pi.is_return == is_return)
        )

        data = query.run(as_dict=True)

        for doc in data:
            doc.fy = self.get_fy(doc.bill_date or doc.posting_date)
            doc._bill_no = self.get_cleaner_bill_no(doc.bill_no, doc.fy)

        return self.get_dict_for_key("supplier_gstin", data)

    def query_purchase_invoice(self, additional_fields=None):
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
            "bill_date",
            "place_of_supply",
            "is_reverse_charge",
            Abs(self.pi.base_rounded_total).as_("document_value"),
        ]

        if additional_fields:
            fields += additional_fields

        return (
            frappe.qb.from_(self.pi)
            .left_join(self.pi_tax)
            .on(self.pi_tax.parent == self.pi.name)
            .where(self.company_gstin == self.pi.company_gstin)
            .where(self.pi.docstatus == 1)
            # Filter for B2B transactions where match can be made
            .where(self.pi.supplier_gstin != "")
            .where(self.pi.gst_category != "Registered Composition")
            .where(self.pi.supplier_gstin.isnotnull())
            .groupby(self.pi.name)
            .select(*tax_fields, *fields)
        )

    def query_tax_amount(self, account):
        return Sum(
            Abs(
                Case()
                .when(
                    self.pi_tax.account_head == account,
                    self.pi_tax.base_tax_amount_after_discount_amount,
                )
                .else_(0)
            )
        )

    def get_inward_supply(self, category, amended_category):
        categories = [category, amended_category or None]
        query = self.query_inward_supply()
        data = (
            query.where(
                (self.gstr2.match_status == "") | (self.gstr2.match_status.isnull())
            )
            .where(self.gstr2.action != "Ignore")
            .where(self.gstr2.classification.isin(categories))
            .run(as_dict=True)
        )

        for doc in data:
            doc.fy = self.get_fy(doc.bill_date)
            doc._bill_no = self.get_cleaner_bill_no(doc.bill_no, doc.fy)
            if doc.classification == amended_category:
                # find B2B
                # change action
                # unmatch with purchase and add match with current B2BA and same status
                # remove it from the list and remove B2B from the list if action in where filters above
                pass

        return self.get_dict_for_key("supplier_gstin", data)

    def query_inward_supply(self, additional_fields=None, for_summary=False):
        fields = self.get_inward_supply_fields(additional_fields, for_summary)
        self.isup_periods = _get_periods(
            self.inward_supply_from_date, self.inward_supply_to_date
        )

        return (
            frappe.qb.from_(self.gstr2)
            .left_join(self.gstr2_item)
            .on(self.gstr2_item.parent == self.gstr2.name)
            .where(self.company_gstin == self.gstr2.company_gstin)
            .where(
                (self.gstr2.return_period_2b.isin(self.isup_periods))
                | (self.gstr2.sup_return_period.isin(self.isup_periods))
            )
            .groupby(self.gstr2_item.parent)
            .select(*fields)
        )

    def get_inward_supply_fields(
        self, additional_fields=None, for_summary=False, table=None
    ):
        """
        Returns fields for inward supply query.

        Column name should be different where we join this query with purchase query.
        Returns column names with 'isup_' prefix for summary where different table is provided.
        """
        if not table:
            table = self.gstr2

        fields = [
            "bill_no",
            "bill_date",
            "document_value",
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
        if table == self.gstr2:
            tax_fields = [
                Sum(self.gstr2_item[field]).as_(
                    f"isup_{field}" if for_summary else field
                )
                for field in GST_TAX_TYPES[:-1]
            ]
        else:
            tax_fields = [
                table[field].as_(f"isup_{field}") for field in GST_TAX_TYPES[:-1]
            ]

        return tax_fields

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
            if data[key] in new_dict:
                new_dict[data[key]].append(data)
            else:
                new_dict[data[key]] = [data]
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
        periods = get_periods(fiscal_year, return_type)
        history = get_import_history(self.company_gstin, return_type, periods)

        columns = [
            "Period",
            "Classification",
            "Status",
            f"{'Downloaded' if for_download else 'Uploaded'} On",
        ]

        data = {}
        for period in periods:
            # TODO: skip if today is not greater than 14th return period's next months
            data[period] = []
            status = "🟢 &nbsp; Downloaded"
            for category in GSTRCategory:
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

    # filters
    # get 2 data sets
    # rules to match data with preference
    @frappe.whitelist()
    def get_date_range(self, period):
        now = datetime.now()
        start_month = end_month = month = now.month
        start_year = end_year = year = now.year
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
        date2 = date2 if date2 < now else now
        return [date1, date2]

    def get_reconciliation_data(self):
        """
        Get Reconciliation data based on standard filters
        Returns
            - Inward Supply: for the return month as per 2A and 2B
            - Purchase Invoice: All invoices matching with inward supply (irrespective of purchase period choosen)
                Unmatched Purchase Invoice for the period choosen
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
            "return_period_2b",
        ]
        inward_supply = self.query_inward_supply(
            isup_additional_fields + ["link_doctype", "link_name"]
        )

        # this will not return missing in inward supply (if any)
        summary_data = (
            purchase.right_join(inward_supply)
            .on(
                (inward_supply.link_doctype == "Purchase Invoice")
                & (inward_supply.link_name == self.pi.name)
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
        summary_data = summary_data + (
            purchase.where(
                self.pi.posting_date[self.purchase_from_date : self.purchase_to_date]
            )
            .where((self.pi.inward_supply == "") | (self.pi.inward_supply.isnull()))
            .run(as_dict=True)
        )
        self.process_reconciliation_data(summary_data)

        return {
            "data": summary_data,
            "columns": self.get_reconciliation_columns(),
        }

    def process_reconciliation_data(self, summary_data):
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
            doc.differences = "<br> ".join(differences)

            # remove columns
            columns_to_remove = [
                "isup_supplier_name",
                "isup_supplier_gstin",
                "isup_place_of_supply",
                "isup_is_reverse_charge",
                "gst_category",
                "is_return",
            ]
            if isinstance(columns_to_remove, str):
                columns_to_remove = (columns_to_remove,)

            for column in columns_to_remove:
                doc.pop(column, None)

        # modify doc
        for doc in summary_data:
            differences = []

            # update missing values
            if not doc.name:
                doc.isup_match_status = "Missing in PR"
                for field in fields_to_update:
                    doc[field] = doc.get(f"isup_{field}", "")

                _update_doc(doc, differences)
                continue

            if not doc.isup_name:
                doc.isup_match_status = "Missing in 2A/2B"
                doc.isup_action = (
                    "Ignore" if doc.pop("ignore_reconciliation", 0) == 1 else ""
                )

                classification = self.GST_CATEGORIES.get(doc.gst_category)
                if doc.is_return and classification == "B2B":
                    classification = "CDNR"

                doc.isup_classification = classification
                _update_doc(doc, differences)
                continue

            # update amount differences
            doc.document_value_diff = round(
                doc.isup_document_value - doc.document_value, 2
            )
            doc.tax_diff = round(
                self.get_total_tax(doc, True) - self.get_total_tax(doc), 2
            )
            self.update_cess_amount(doc)

            if doc.isup_match_status not in ["Mismatch", "Manual Match"]:
                if abs(doc.tax_diff) > 0.01 or abs(doc.document_value_diff) > 0.01:
                    differences.append("Rounding Difference")

                _update_doc(doc, differences)
                continue

            # update differences
            for field in self.FIELDS_TO_MATCH:
                isup_value = doc.get(f"isup_{field}")
                label = frappe.unscrub(field)

                if isinstance(doc.get(field), str):
                    label = f"{label} - {isup_value}"

                if isup_value != doc.get(field):
                    differences.append(label)

            _update_doc(doc, differences)

    def get_reconciliation_columns(self):
        return [
            {
                "fieldname": "name",
                "label": "Purchase Invoice",
                "fieldtype": "Link",
                "options": "Purchase Invoice",
            },
            {
                "fieldname": "supplier",
                "label": "Supplier",
                "fieldtype": "Link",
                "options": "Supplier",
            },
            {
                "fieldname": "supplier_name",
                "label": "Supplier Name",
            },
            {
                "fieldname": "supplier_gstin",
                "label": "Supplier GSTIN",
            },
            {
                "fieldname": "bill_no",
                "label": "Bill No",
            },
            {
                "fieldname": "bill_date",
                "label": "Bill Date",
                "fieldtype": "Date",
            },
            {
                "fieldname": "place_of_supply",
                "label": "Place of Supply",
            },
            {
                "fieldname": "is_reverse_charge",
                "label": "Reverse Charge",
                "fieldtype": "Check",
            },
            {
                "fieldname": "cgst",
                "label": "CGST",
                "fieldtype": "Float",
            },
            {
                "fieldname": "sgst",
                "label": "SGST",
                "fieldtype": "Float",
            },
            {
                "fieldname": "igst",
                "label": "IGST",
                "fieldtype": "Float",
            },
            {
                "fieldname": "cess",
                "label": "CESS",
                "fieldtype": "Float",
            },
            {
                "fieldname": "document_value",
                "label": "Document Value",
                "fieldtype": "Float",
            },
            {
                "fieldname": "isup_name",
                "label": "Inward Supply",
                "fieldtype": "Link",
                "options": "Inward Supply",
            },
            {
                "fieldname": "isup_bill_no",
                "label": "GSTR Bill No",
            },
            {
                "fieldname": "isup_bill_date",
                "label": "GSTR Bill Date",
                "fieldtype": "Date",
            },
            {
                "fieldname": "isup_cgst",
                "label": "GSTR CGST",
                "fieldtype": "Float",
            },
            {
                "fieldname": "isup_sgst",
                "label": "GSTR SGST",
                "fieldtype": "Float",
            },
            {
                "fieldname": "isup_igst",
                "label": "GSTR IGST",
                "fieldtype": "Float",
            },
            {
                "fieldname": "isup_cess",
                "label": "GSTR CESS",
                "fieldtype": "Float",
            },
            {
                "fieldname": "isup_document_value",
                "label": "GSTR Document Value",
                "fieldtype": "Float",
            },
            {
                "fieldname": "isup_classification",
                "label": "Category",
                "fieldtype": "Select",
                "options": [cat.value for cat in GSTRCategory],
            },
            {
                "fieldname": "isup_match_status",
                "label": "Match Status",
                "fieldtype": "Select",
                "options": [
                    "Exact Match",
                    "Suggested Match",
                    "Mismatch",
                    "Manual Match",
                    "Missing in 2A/2B",
                    "Missing in PR",
                ],
            },
            {
                "fieldname": "isup_action",
                "label": "Action",
                "fieldtype": "Select",
                "options": [
                    "No Action",
                    "Accept My Values",
                    "Accept Supplier Values",
                    "Ignore",
                    "Pending",
                ],
            },
            {
                "fieldname": "isup_return_period_2b",
                "label": "Return Period 2B",
                "fieldtype": "select",
                "options": self.isup_periods,
            },
            {
                "fieldname": "tax_diff",
                "label": "Tax Difference",
                "fieldtype": "Float",
            },
            {
                "fieldname": "document_value_diff",
                "label": "Document Value Difference",
                "fieldtype": "Float",
            },
            {
                "fieldname": "differences",
                "label": "Differences",
            },
        ]


def get_periods(fiscal_year, return_type: ReturnType):
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
    return tuple(reversed(_get_periods(fiscal_year.start_date, end_date)))


def _get_periods(start_date, end_date):
    """Returns a list of month (formatted as `MMYYYY`) in given date range"""

    if isinstance(start_date, str):
        start_date = getdate(start_date)

    if isinstance(end_date, str):
        end_date = getdate(end_date)

    return [
        dt.strftime("%m%Y") for dt in rrule(MONTHLY, dtstart=start_date, until=end_date)
    ]


def _getdate(return_type):
    if return_type == ReturnType.GSTR2B:
        if getdate().day >= GSTR2B_GEN_DATE:
            return add_months(getdate(), -1)
        else:
            return add_months(getdate(), -2)

    return getdate()


def _get_first_day(month, year):
    """Returns first day of the month"""
    return datetime(year, month, 1)


def _get_last_day(month, year):
    """Returns last day of the month"""
    return datetime(year, month, monthrange(year, month)[1])


def get_import_history(
    company_gstin, return_type: ReturnType, periods: List[str], fields=None, pluck=None
):
    if not (fields or pluck):
        fields = (
            "return_period",
            "classification",
            "data_not_found",
            "last_updated_on",
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
