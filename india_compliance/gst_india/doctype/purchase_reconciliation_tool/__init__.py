# Copyright (c) 2022, Resilient Tech and contributors
# For license information, please see license.txt

from enum import Enum

from dateutil.rrule import MONTHLY, rrule
from rapidfuzz import fuzz, process

import frappe
from frappe.query_builder import Case
from frappe.query_builder.functions import Abs, Sum
from frappe.utils import add_months, getdate, rounded

from india_compliance.gst_india.constants import GST_TAX_TYPES
from india_compliance.gst_india.utils import (
    get_gst_accounts_by_type,
    get_party_for_gstin,
)
from india_compliance.gst_india.utils.gstr import ReturnType


class Fields(Enum):
    FISCAL_YEAR = "fy"
    SUPPLIER_GSTIN = "supplier_gstin"
    BILL_NO = "bill_no"
    PLACE_OF_SUPPLY = "place_of_supply"
    REVERSE_CHARGE = "is_reverse_charge"
    TAXABLE_VALUE = "taxable_value"
    CGST = "cgst"
    SGST = "sgst"
    IGST = "igst"
    CESS = "cess"


class Rule(Enum):
    EXACT_MATCH = "Exact Match"
    FUZZY_MATCH = "Fuzzy Match"
    MISMATCH = "Mismatch"
    ROUNDING_DIFFERENCE = "Rounding Difference"  # <= 1 hardcoded


class MatchStatus(Enum):
    EXACT_MATCH = "Exact Match"
    SUGGESTED_MATCH = "Suggested Match"
    MISMATCH = "Mismatch"
    RESIDUAL_MATCH = "Residual Match"
    MANUAL_MATCH = "Manual Match"
    MISSING_IN_PI = "Missing in PI"
    MISSING_IN_2A_2B = "Missing in 2A/2B"


# Summary of rules:
# GSTIN_RULES = [
#     {"Exact Match": ["E", "E", "E", "E", "E", 0, 0, 0, 0, 0]},
#     {"Suggested Match": ["E", "E", "F", "E", "E", 0, 0, 0, 0, 0]},
#     {"Suggested Match": ["E", "E", "E", "E", "E", 1, 1, 1, 1, 2]},
#     {"Suggested Match": ["E", "E", "F", "E", "E", 1, 1, 1, 1, 2]},
#     {"Mismatch": ["E", "E", "E", "N", "N", "N", "N", "N", "N", "N"]},
#     {"Mismatch": ["E", "E", "F", "N", "N", "N", "N", "N", "N", "N"]},
#     {"Residual Match": ["E", "E", "N", "E", "E", 1, 1, 1, 1, 2]},
# ]

# PAN_RULES = [
#     {"Mismatch": ["E", "N", "E", "E", "E", 1, 1, 1, 1, 2]},
#     {"Mismatch": ["E", "N", "F", "E", "E", 1, 1, 1, 1, 2]},
#     {"Mismatch": ["E", "N", "F", "N", "N", "N", "N", "N", "N", "N"]},
#     {"Residual Match": ["E", "N", "N", "E", "E", 1, 1, 1, 1, 2]},
# ]


class GSTINRules(Enum):
    RULE1 = {
        "match_status": MatchStatus.EXACT_MATCH,
        "rule": {
            Fields.FISCAL_YEAR: Rule.EXACT_MATCH,
            Fields.SUPPLIER_GSTIN: Rule.EXACT_MATCH,
            Fields.BILL_NO: Rule.EXACT_MATCH,
            Fields.PLACE_OF_SUPPLY: Rule.EXACT_MATCH,
            Fields.REVERSE_CHARGE: Rule.EXACT_MATCH,
            Fields.TAXABLE_VALUE: Rule.EXACT_MATCH,
            Fields.CGST: Rule.EXACT_MATCH,
            Fields.SGST: Rule.EXACT_MATCH,
            Fields.IGST: Rule.EXACT_MATCH,
            Fields.CESS: Rule.EXACT_MATCH,
        },
    }

    RULE2 = {
        "match_status": MatchStatus.SUGGESTED_MATCH,
        "rule": {
            Fields.FISCAL_YEAR: Rule.EXACT_MATCH,
            Fields.SUPPLIER_GSTIN: Rule.EXACT_MATCH,
            Fields.BILL_NO: Rule.FUZZY_MATCH,
            Fields.PLACE_OF_SUPPLY: Rule.EXACT_MATCH,
            Fields.REVERSE_CHARGE: Rule.EXACT_MATCH,
            Fields.TAXABLE_VALUE: Rule.EXACT_MATCH,
            Fields.CGST: Rule.EXACT_MATCH,
            Fields.SGST: Rule.EXACT_MATCH,
            Fields.IGST: Rule.EXACT_MATCH,
            Fields.CESS: Rule.EXACT_MATCH,
        },
    }

    RULE3 = {
        "match_status": MatchStatus.SUGGESTED_MATCH,
        "rule": {
            Fields.FISCAL_YEAR: Rule.EXACT_MATCH,
            Fields.SUPPLIER_GSTIN: Rule.EXACT_MATCH,
            Fields.BILL_NO: Rule.EXACT_MATCH,
            Fields.PLACE_OF_SUPPLY: Rule.EXACT_MATCH,
            Fields.REVERSE_CHARGE: Rule.EXACT_MATCH,
            Fields.TAXABLE_VALUE: Rule.ROUNDING_DIFFERENCE,
            Fields.CGST: Rule.ROUNDING_DIFFERENCE,
            Fields.SGST: Rule.ROUNDING_DIFFERENCE,
            Fields.IGST: Rule.ROUNDING_DIFFERENCE,
            Fields.CESS: Rule.ROUNDING_DIFFERENCE,
        },
    }

    RULE4 = {
        "match_status": MatchStatus.SUGGESTED_MATCH,
        "rule": {
            Fields.FISCAL_YEAR: Rule.EXACT_MATCH,
            Fields.SUPPLIER_GSTIN: Rule.EXACT_MATCH,
            Fields.BILL_NO: Rule.FUZZY_MATCH,
            Fields.PLACE_OF_SUPPLY: Rule.EXACT_MATCH,
            Fields.REVERSE_CHARGE: Rule.EXACT_MATCH,
            Fields.TAXABLE_VALUE: Rule.ROUNDING_DIFFERENCE,
            Fields.CGST: Rule.ROUNDING_DIFFERENCE,
            Fields.SGST: Rule.ROUNDING_DIFFERENCE,
            Fields.IGST: Rule.ROUNDING_DIFFERENCE,
            Fields.CESS: Rule.ROUNDING_DIFFERENCE,
        },
    }

    RULE5 = {
        "match_status": MatchStatus.MISMATCH,
        "rule": {
            Fields.FISCAL_YEAR: Rule.EXACT_MATCH,
            Fields.SUPPLIER_GSTIN: Rule.EXACT_MATCH,
            Fields.BILL_NO: Rule.EXACT_MATCH,
            # Fields.PLACE_OF_SUPPLY: Rule.MISMATCH,
            # Fields.IS_REVERSE_CHARGE: Rule.MISMATCH,
            # Fields.TAXABLE_VALUE: Rule.MISMATCH,
            # Fields.CGST: Rule.MISMATCH,
            # Fields.SGST: Rule.MISMATCH,
            # Fields.IGST: Rule.MISMATCH,
            # Fields.CESS: Rule.MISMATCH,
        },
    }

    RULE6 = {
        "match_status": MatchStatus.MISMATCH,
        "rule": {
            Fields.FISCAL_YEAR: Rule.EXACT_MATCH,
            Fields.SUPPLIER_GSTIN: Rule.EXACT_MATCH,
            Fields.BILL_NO: Rule.FUZZY_MATCH,
            # Fields.PLACE_OF_SUPPLY: Rule.MISMATCH,
            # Fields.IS_REVERSE_CHARGE: Rule.MISMATCH,
            # Fields.TAXABLE_VALUE: Rule.MISMATCH,
            # Fields.CGST: Rule.MISMATCH,
            # Fields.SGST: Rule.MISMATCH,
            # Fields.IGST: Rule.MISMATCH,
            # Fields.CESS: Rule.MISMATCH,
        },
    }

    RULE7 = {
        "match_status": MatchStatus.RESIDUAL_MATCH,
        "rule": {
            Fields.FISCAL_YEAR: Rule.EXACT_MATCH,
            Fields.SUPPLIER_GSTIN: Rule.EXACT_MATCH,
            # Fields.BILL_NO: Rule.MISMATCH,
            Fields.PLACE_OF_SUPPLY: Rule.EXACT_MATCH,
            Fields.REVERSE_CHARGE: Rule.EXACT_MATCH,
            Fields.TAXABLE_VALUE: Rule.ROUNDING_DIFFERENCE,
            Fields.CGST: Rule.ROUNDING_DIFFERENCE,
            Fields.SGST: Rule.ROUNDING_DIFFERENCE,
            Fields.IGST: Rule.ROUNDING_DIFFERENCE,
            Fields.CESS: Rule.ROUNDING_DIFFERENCE,
        },
    }


class PANRules(Enum):
    RULE1 = {
        "match_status": MatchStatus.MISMATCH,
        "rule": {
            Fields.FISCAL_YEAR: Rule.EXACT_MATCH,
            # Fields.SUPPLIER_GSTIN: Rule.MISMATCH,
            Fields.BILL_NO: Rule.EXACT_MATCH,
            Fields.PLACE_OF_SUPPLY: Rule.EXACT_MATCH,
            Fields.REVERSE_CHARGE: Rule.EXACT_MATCH,
            Fields.TAXABLE_VALUE: Rule.ROUNDING_DIFFERENCE,
            Fields.CGST: Rule.ROUNDING_DIFFERENCE,
            Fields.SGST: Rule.ROUNDING_DIFFERENCE,
            Fields.IGST: Rule.ROUNDING_DIFFERENCE,
            Fields.CESS: Rule.ROUNDING_DIFFERENCE,
        },
    }

    RULE2 = {
        "match_status": MatchStatus.MISMATCH,
        "rule": {
            Fields.FISCAL_YEAR: Rule.EXACT_MATCH,
            # Fields.SUPPLIER_GSTIN: Rule.MISMATCH,
            Fields.BILL_NO: Rule.FUZZY_MATCH,
            Fields.PLACE_OF_SUPPLY: Rule.EXACT_MATCH,
            Fields.REVERSE_CHARGE: Rule.EXACT_MATCH,
            Fields.TAXABLE_VALUE: Rule.ROUNDING_DIFFERENCE,
            Fields.CGST: Rule.ROUNDING_DIFFERENCE,
            Fields.SGST: Rule.ROUNDING_DIFFERENCE,
            Fields.IGST: Rule.ROUNDING_DIFFERENCE,
            Fields.CESS: Rule.ROUNDING_DIFFERENCE,
        },
    }

    RULE3 = {
        "match_status": MatchStatus.MISMATCH,
        "rule": {
            Fields.FISCAL_YEAR: Rule.EXACT_MATCH,
            # Fields.SUPPLIER_GSTIN: Rule.MISMATCH,
            Fields.BILL_NO: Rule.FUZZY_MATCH,
            # Fields.PLACE_OF_SUPPLY: Rule.MISMATCH,
            # Fields.IS_REVERSE_CHARGE: Rule.MISMATCH,
            # Fields.TAXABLE_VALUE: Rule.MISMATCH,
            # Fields.CGST: Rule.MISMATCH,
            # Fields.SGST: Rule.MISMATCH,
            # Fields.IGST: Rule.MISMATCH,
            # Fields.CESS: Rule.MISMATCH,
        },
    }

    RULE4 = {
        "match_status": MatchStatus.RESIDUAL_MATCH,
        "rule": {
            Fields.FISCAL_YEAR: Rule.EXACT_MATCH,
            # Fields.SUPPLIER_GSTIN: Rule.MISMATCH,
            # Fields.BILL_NO: Rule.MISMATCH,
            Fields.PLACE_OF_SUPPLY: Rule.EXACT_MATCH,
            Fields.REVERSE_CHARGE: Rule.EXACT_MATCH,
            Fields.TAXABLE_VALUE: Rule.ROUNDING_DIFFERENCE,
            Fields.CGST: Rule.ROUNDING_DIFFERENCE,
            Fields.SGST: Rule.ROUNDING_DIFFERENCE,
            Fields.IGST: Rule.ROUNDING_DIFFERENCE,
            Fields.CESS: Rule.ROUNDING_DIFFERENCE,
        },
    }


class InwardSupply:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

        self.GSTR2 = frappe.qb.DocType("GST Inward Supply")
        self.GSTR2_ITEM = frappe.qb.DocType("GST Inward Supply Item")

    def get_all(self, additional_fields=None, names=None, only_names=False):
        query = self.with_period_filter(additional_fields)
        if only_names and not names:
            return

        elif names:
            query = query.where(self.GSTR2.name.isin(names))

        return query.run(as_dict=True)

    def get_unmatched(self, category, amended_category):
        categories = [category, amended_category or None]
        query = self.with_period_filter()
        data = (
            query.where(
                (self.GSTR2.match_status == "") | (self.GSTR2.match_status.isnull())
            )
            .where(self.GSTR2.action != "Ignore")
            .where(self.GSTR2.classification.isin(categories))
            .run(as_dict=True)
        )

        for doc in data:
            doc.fy = BaseUtil.get_fy(doc.bill_date)
            doc._bill_no = BaseUtil.get_cleaner_bill_no(doc.bill_no, doc.fy)

        return BaseUtil.get_dict_for_key("supplier_gstin", data)

    def with_period_filter(self, additional_fields=None):
        query = self.get_query(additional_fields)
        periods = BaseUtil._get_periods(self.from_date, self.to_date)

        if self.gst_return == "GSTR 2B":
            query = query.where((self.GSTR2.return_period_2b.isin(periods)))
        else:
            query = query.where(
                (self.GSTR2.return_period_2b.isin(periods))
                | (self.GSTR2.sup_return_period.isin(periods))
                | (self.GSTR2.other_return_period.isin(periods))
            )

        return query

    def get_query(self, additional_fields=None):
        """
        Query without filtering for return period
        """
        fields = self.get_fields(additional_fields)
        query = (
            frappe.qb.from_(self.GSTR2)
            .left_join(self.GSTR2_ITEM)
            .on(self.GSTR2_ITEM.parent == self.GSTR2.name)
            .where(self.company_gstin == self.GSTR2.company_gstin)
            .where(self.GSTR2.match_status != "Amended")
            .groupby(self.GSTR2_ITEM.parent)
            .select(*fields)
        )
        return query

    def get_fields(self, additional_fields=None, table=None):
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

        fields = [table[field] for field in fields]
        fields += self.get_tax_fields(table)

        return fields

    def get_tax_fields(self, table):
        fields = GST_TAX_TYPES[:-1] + ("taxable_value",)

        if table == frappe.qb.DocType("GST Inward Supply"):
            return [Sum(self.GSTR2_ITEM[field]).as_(field) for field in fields]

        return [table[field] for field in fields]


class PurchaseInvoice:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

        self.PI = frappe.qb.DocType("Purchase Invoice")
        self.PI_TAX = frappe.qb.DocType("Purchase Taxes and Charges")

    def get_all(self, additional_fields=None, names=None, only_names=False):
        query = self.get_query(additional_fields)

        if only_names and not names:
            return

        elif only_names:
            query = query.where(self.PI.name.isin(names))

        elif names:
            query = query.where(
                (self.PI.posting_date[self.from_date : self.to_date])
                | (self.PI.name.isin(names))
            )

        else:
            query = query.where(self.PI.posting_date[self.from_date : self.to_date])

        return query.run(as_dict=True)

    def get_unmatched(self, category):
        gst_category = (
            ("Registered Regular", "Tax Deductor")
            if category in ("B2B", "CDNR", "ISD")
            else ("SEZ", "Overseas", "UIN Holders")
        )
        is_return = 1 if category == "CDNR" else 0

        query = (
            self.get_query(is_return=is_return)
            .where(self.PI.posting_date[self.from_date : self.to_date])
            .where(
                self.PI.name.notin(
                    PurchaseInvoice.query_matched_purchase_invoice(
                        self.from_date, self.to_date
                    )
                )
            )
            .where(self.PI.ignore_reconciliation == 0)
            .where(self.PI.gst_category.isin(gst_category))
            .where(self.PI.is_return == is_return)
        )

        data = query.run(as_dict=True)

        for doc in data:
            doc.fy = BaseUtil.get_fy(doc.bill_date or doc.posting_date)
            doc._bill_no = BaseUtil.get_cleaner_bill_no(doc.bill_no, doc.fy)

        return BaseUtil.get_dict_for_key("supplier_gstin", data)

    def get_query(self, additional_fields=None, is_return=False):
        PI_ITEM = frappe.qb.DocType("Purchase Invoice Item")

        fields = self.get_fields(additional_fields, is_return)
        pi_item = (
            frappe.qb.from_(PI_ITEM)
            .select(
                Abs(Sum(PI_ITEM.taxable_value)).as_("taxable_value"),
                PI_ITEM.parent,
            )
            .groupby(PI_ITEM.parent)
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
            .select(*fields, pi_item.taxable_value)
        )

    def get_fields(self, additional_fields=None, is_return=False):
        gst_accounts = get_gst_accounts_by_type(self.company, "Input")
        tax_fields = [
            self.query_tax_amount(account).as_(tax[:-8])
            for tax, account in gst_accounts.items()
        ]

        fields = [
            "name",
            "supplier_gstin",
            "bill_no",
            "place_of_supply",
            "is_reverse_charge",
            *tax_fields,
        ]

        if is_return:
            # return is initiated by the customer. So bill date may not be available or known.
            fields += [self.PI.posting_date.as_("bill_date")]
        else:
            fields += ["bill_date"]

        if additional_fields:
            fields += additional_fields

        return fields

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

    @staticmethod
    def query_matched_purchase_invoice(from_date=None, to_date=None):
        GSTR2 = frappe.qb.DocType("GST Inward Supply")
        PI = frappe.qb.DocType("Purchase Invoice")

        query = (
            frappe.qb.from_(GSTR2)
            .select("link_name")
            .where(GSTR2.link_doctype == "Purchase Invoice")
            .join(PI)
            .on(PI.name == GSTR2.link_name)
        )

        if from_date and to_date:
            query = query.where(PI.posting_date[from_date:to_date])

        return query


class BaseReconciliation:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def get_all_inward_supply(
        self, additional_fields=None, names=None, only_names=False
    ):
        return InwardSupply(
            company_gstin=self.company_gstin,
            from_date=self.inward_supply_from_date,
            to_date=self.inward_supply_to_date,
            gst_return=self.gst_return,
        ).get_all(additional_fields, names, only_names)

    def get_unmatched_inward_supply(self, category, amended_category):
        return InwardSupply(
            company_gstin=self.company_gstin,
            from_date=self.inward_supply_from_date,
            to_date=self.inward_supply_to_date,
            gst_return=self.gst_return,
        ).get_unmatched(category, amended_category)

    def query_inward_supply(self, additional_fields=None):
        query = InwardSupply(
            company_gstin=self.company_gstin,
            from_date=self.inward_supply_from_date,
            to_date=self.inward_supply_to_date,
            gst_return=self.gst_return,
        )

        return query.with_period_filter(additional_fields)

    def get_all_purchase_invoice(
        self, additional_fields=None, names=None, only_names=False
    ):
        return PurchaseInvoice(
            company=self.company,
            company_gstin=self.company_gstin,
            from_date=self.purchase_from_date,
            to_date=self.purchase_to_date,
        ).get_all(additional_fields, names, only_names)

    def get_unmatched_purchase(self, category):
        return PurchaseInvoice(
            company=self.company,
            company_gstin=self.company_gstin,
            from_date=self.purchase_from_date,
            to_date=self.purchase_to_date,
        ).get_unmatched(category)

    def query_purchase_invoice(self, additional_fields=None):
        return PurchaseInvoice(
            company=self.company, company_gstin=self.company_gstin
        ).get_query(additional_fields)


class Reconciler(BaseReconciliation):
    def reconcile(self, category, amended_category):
        """
        Reconcile purchases and inward supplies for given category.
        """
        # GSTIN Level matching
        purchases = self.get_unmatched_purchase(category)
        inward_supplies = self.get_unmatched_inward_supply(category, amended_category)
        self.reconcile_for_rules(GSTINRules, purchases, inward_supplies, category)

        # PAN Level matching
        purchases = self.get_pan_level_data(purchases)
        inward_supplies = self.get_pan_level_data(inward_supplies)
        self.reconcile_for_rules(PANRules, purchases, inward_supplies, category)

    def reconcile_for_rules(self, rules, purchases, inward_supplies, category):
        if not (purchases and inward_supplies):
            return

        for rule in rules:
            rule = rule.value
            self.reconcile_for_rule(
                purchases,
                inward_supplies,
                rule.get("match_status"),
                rule.get("rule"),
                category,
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
        for doc in data1.values():
            summary.setdefault(doc.bill_date.month, 0)
            summary[doc.bill_date.month] += self.get_total_tax(doc)

        for doc in data2.values():
            summary.setdefault(doc.bill_date.month, 0)
            summary[doc.bill_date.month] -= self.get_total_tax(doc)

        return summary

    def is_doc_matching(self, pur, isup, rules):
        """
        Returns true if all fields match from purchase and inward supply as per rules.

        param pur: purchase doc
        param isup: inward supply doc
        param rules: dict of rule against field to match
        """

        for field, rule in rules.items():
            if not self.is_field_matching(pur, isup, field.value, rule):
                return False

        return True

    def is_field_matching(self, pur, isup, field, rule):
        """
        Returns true if the field matches from purchase and inward supply as per the rule.

        param pur: purchase doc
        param isup: inward supply doc
        param field: field to match
        param rule: rule applied to match
        """

        if rule == Rule.EXACT_MATCH:
            return pur[field] == isup[field]
        elif rule == Rule.FUZZY_MATCH:
            return self.fuzzy_match(pur, isup)
        elif rule == Rule.ROUNDING_DIFFERENCE:
            return self.get_amount_difference(pur, isup, field) <= 1

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
            BaseUtil.update_cess_amount(pur)

        return abs(pur.get(field, 0) - isup.get(field, 0))

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

    def get_pan_level_data(self, data):
        out = {}
        for gstin, invoices in data.items():
            pan = gstin[2:-3]
            out.setdefault(pan, {})
            out[pan].update(invoices)

        return out


class ReconciledData(BaseReconciliation):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.gstin_party_map = frappe._dict()

    def get_consolidated_data(
        self,
        purchase_names: list = None,
        inward_supply_names: list = None,
        prefix: str = None,
    ):
        data = self.get(purchase_names, inward_supply_names)
        for doc in data:
            purchase = doc.pop("_purchase_invoice", frappe._dict())
            inward_supply = doc.pop("_inward_supply", frappe._dict())

            doc.update(purchase)
            doc.update(
                {f"{prefix}_{key}": value for key, value in inward_supply.items()}
            )

        return data

    def get_manually_matched_data(self, purchase_name: str, inward_supply_name: str):
        """
        Get manually matched data for given purchase invoice and inward supply.
        This can be used to show comparision of matched values.
        """
        inward_supplies = self.get_all_inward_supply(
            [inward_supply_name], only_names=True
        )
        purchases = self.get_all_purchase_invoice("", [purchase_name], only_names=True)

        reconciliation_data = [
            frappe._dict(
                {
                    "_inward_supply": inward_supplies[0]
                    if inward_supplies
                    else frappe._dict(),
                    "_purchase_invoice": purchases.get(purchase_name, frappe._dict()),
                }
            )
        ]
        self.process_data(reconciliation_data, retain_doc=True)
        return reconciliation_data[0]

    def get(self, purchase_names: list = None, inward_supply_names: list = None):
        # TODO: update cess amount in purchase invoice
        """
        Get Reconciliation data based on standard filters
        Returns
            - Inward Supply: for the return month as per 2A and 2B
            - Purchase Invoice: All invoices matching with inward supply (irrespective of purchase period choosen)
                Unmatched Purchase Invoice for the period choosen

        """

        retain_doc = only_names = False
        if inward_supply_names or purchase_names:
            retain_doc = only_names = True

        inward_supplies = self.get_all_inward_supply(inward_supply_names)
        purchases = self.get_all_purchase_invoice(
            inward_supplies, purchase_names, only_names
        )

        reconciliation_data = []
        for doc in inward_supplies:
            reconciliation_data.append(
                frappe._dict(
                    {
                        "_inward_supply": doc,
                        "_purchase_invoice": purchases.pop(
                            doc.link_name, frappe._dict()
                        ),
                    }
                )
            )

        for doc in purchases.values():
            reconciliation_data.append(frappe._dict({"_purchase_invoice": doc}))

        self.process_data(reconciliation_data, retain_doc=retain_doc)
        return reconciliation_data

    def get_all_inward_supply(self, inward_supply_names=None, only_names=False):
        inward_supply_fields = [
            "supplier_name",
            "classification",
            "match_status",
            "action",
            "link_doctype",
            "link_name",
        ]

        return super().get_all_inward_supply(
            inward_supply_fields, inward_supply_names, only_names
        )

    def get_all_purchase_invoice(
        self, inward_supplies, purchase_names, only_names=False
    ):
        purchase_fields = [
            "supplier",
            "supplier_name",
            "is_return",
            "gst_category",
            "ignore_reconciliation",
        ]

        if not only_names:
            purchase_names = set()
            for doc in inward_supplies:
                if doc.link_doctype == "Purchase Invoice":
                    purchase_names.add(doc.link_name)

        purchases = super().get_all_purchase_invoice(
            purchase_fields, purchase_names, only_names
        )

        if not purchases:
            return {}

        return {doc.name: doc for doc in purchases}

    def process_data(self, reconciliation_data: list, retain_doc: bool = False):
        """
        Process reconciliation data to add additional fields or update differences.
        Cases:
            - Missing in Purchase Invoice
            - Missing in Inward Supply
            - Update differences

        params:
            - reconciliation_data: list of reconciliation data
            Format:
                [
                    {
                        "_purchase_invoice": purchase invoice doc,
                        "_inward_supply": inward supply doc,
                    },
                    ...
                ]

            - retain_doc: retain vs pop doc from reconciliation data

        """
        default_dict = {
            "supplier_name": "",
            "supplier_gstin": "",
            "bill_no": "",
            "bill_date": "",
            "match_status": "",
            "purchase_invoice_name": "",
            "inward_supply_name": "",
            "taxable_value_difference": "",
            "tax_difference": "",
            "differences": "",
            "action": "",
            "classification": "",
        }

        for data in reconciliation_data:
            data.update(default_dict)
            method = data.get if retain_doc else data.pop

            purchase = method("_purchase_invoice", frappe._dict())
            inward_supply = method("_inward_supply", frappe._dict())

            self.update_fields(data, purchase, inward_supply)
            self.update_amount_difference(data, purchase, inward_supply)
            self.update_differences(data, purchase, inward_supply)

    def update_fields(self, data, purchase, inward_supply):
        for field in ("supplier_name", "supplier_gstin", "bill_no", "bill_date"):
            data[field] = purchase.get(field) or inward_supply.get(field)

        data.update(
            {
                "supplier_name": data.supplier_name
                or self.guess_supplier_name(data.supplier_gstin),
                "purchase_invoice_name": purchase.get("name"),
                "inward_supply_name": inward_supply.get("name"),
                "match_status": inward_supply.get("match_status"),
                "action": inward_supply.get("action"),
                "classification": inward_supply.get("classification")
                or self.guess_classification(purchase),
            }
        )

        # missing in purchase invoice
        if not purchase:
            data.match_status = MatchStatus.MISSING_IN_PI.value

        # missing in inward supply
        elif not inward_supply:
            data.match_status = MatchStatus.MISSING_IN_2A_2B.value
            data.action = (
                "Ignore" if purchase.get("ignore_reconciliation") else "No Action"
            )

    def update_amount_difference(self, data, purchase, inward_supply):
        data.taxable_value_difference = rounded(
            purchase.get("taxable_value", 0) - inward_supply.get("taxable_value", 0),
            2,
        )

        data.tax_difference = rounded(
            BaseUtil.get_total_tax(purchase) - BaseUtil.get_total_tax(inward_supply),
            2,
        )

    def update_differences(self, data, purchase, inward_supply):
        differences = []
        if self.is_exact_or_suggested_match(data):
            if self.has_rounding_difference(data):
                differences.append("Rounding Difference")

        elif not self.is_mismatch_or_manual_match(data):
            return

        for field in Fields:
            if field == Fields.BILL_NO:
                continue

            if purchase.get(field.value) != inward_supply.get(field.value):
                differences.append(field.name)

        data.differences = ", ".join(differences)

    def guess_supplier_name(self, gstin):
        if party := self.gstin_party_map.get(gstin):
            return party

        return self.gstin_party_map.setdefault(
            gstin, get_party_for_gstin(gstin) or "Unknown"
        )

    @staticmethod
    def guess_classification(doc):
        GST_CATEGORIES = {
            "Registered Regular": "B2B",
            "SEZ": "IMPGSEZ",
            "Overseas": "IMPG",
            "UIN Holders": "B2B",
            "Tax Deductor": "B2B",
        }

        classification = GST_CATEGORIES.get(doc.gst_category)
        if doc.is_return and classification == "B2B":
            classification = "CDNR"

        return classification

    @staticmethod
    def is_exact_or_suggested_match(data):
        return data.match_status in (
            MatchStatus.EXACT_MATCH.value,
            MatchStatus.SUGGESTED_MATCH.value,
        )

    @staticmethod
    def is_mismatch_or_manual_match(data):
        return data.match_status in (
            MatchStatus.MISMATCH.value,
            MatchStatus.MANUAL_MATCH.value,
        )

    @staticmethod
    def has_rounding_difference(data):
        return (
            abs(data.taxable_value_difference) > 0.01 or abs(data.tax_difference) > 0.01
        )


class BaseUtil:
    @staticmethod
    def get_fy(date):
        if not date:
            return

        # Standard for India as per GST
        if date.month < 4:
            return f"{date.year - 1}-{date.year}"

        return f"{date.year}-{date.year + 1}"

    @staticmethod
    def get_cleaner_bill_no(bill_no, fy):
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

    @staticmethod
    def get_dict_for_key(key, list):
        new_dict = frappe._dict()
        for data in list:
            new_dict.setdefault(data[key], {})[data.name] = data

        return new_dict

    @staticmethod
    def get_total_tax(doc):
        total_tax = 0

        for tax in GST_TAX_TYPES:
            total_tax += doc.get(tax, 0)

        return total_tax

    @staticmethod
    def update_cess_amount(doc):
        doc.cess = doc.get("cess", 0) + doc.get("cess_non_advol", 0)

    @staticmethod
    def get_periods(date_range, return_type: ReturnType, reversed=False):
        """Returns a list of month (formatted as `MMYYYY`) in a fiscal year"""
        if not date_range:
            return []

        date_range = (getdate(date_range[0]), getdate(date_range[1]))
        end_date = min(date_range[1], BaseUtil._getdate(return_type))

        # latest to oldest
        return tuple(
            BaseUtil._reversed(BaseUtil._get_periods(date_range[0], end_date), reversed)
        )

    @staticmethod
    def _get_periods(start_date, end_date):
        """Returns a list of month (formatted as `MMYYYY`) in given date range"""

        if isinstance(start_date, str):
            start_date = getdate(start_date)

        if isinstance(end_date, str):
            end_date = getdate(end_date)

        return [
            dt.strftime("%m%Y")
            for dt in rrule(MONTHLY, dtstart=start_date, until=end_date)
        ]

    @staticmethod
    def _reversed(lst, reverse):
        if reverse:
            return reversed(lst)
        return lst

    @staticmethod
    def _getdate(return_type):
        GSTR2B_GEN_DATE = 14
        if return_type == ReturnType.GSTR2B:
            if getdate().day >= GSTR2B_GEN_DATE:
                return add_months(getdate(), -1)
            else:
                return add_months(getdate(), -2)

        return getdate()
