# Copyright (c) 2022, Resilient Tech and contributors
# For license information, please see license.txt

from enum import Enum

from dateutil.rrule import MONTHLY, rrule
from rapidfuzz import fuzz, process

import frappe
from frappe.query_builder import Case
from frappe.query_builder.custom import ConstantColumn
from frappe.query_builder.functions import Abs, IfNull, Sum
from frappe.utils import add_months, format_date, getdate, rounded

from india_compliance.gst_india.constants import GST_TAX_TYPES
from india_compliance.gst_india.utils import (
    get_escaped_name,
    get_gst_accounts_by_type,
    get_party_for_gstin,
)
from india_compliance.gst_india.utils.gstr import IMPORT_CATEGORY, ReturnType


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
    TOTAL_GST = "total_gst"


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

GSTIN_RULES = (
    {
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
    },
    {
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
    },
    {
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
    },
    {
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
    },
    {
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
    },
    {
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
    },
    {
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
    },
)


PAN_RULES = (
    {
        "match_status": MatchStatus.MISMATCH,
        "rule": {
            Fields.FISCAL_YEAR: Rule.EXACT_MATCH,
            # Fields.SUPPLIER_GSTIN: Rule.MISMATCH,
            Fields.BILL_NO: Rule.EXACT_MATCH,
            Fields.PLACE_OF_SUPPLY: Rule.EXACT_MATCH,
            Fields.REVERSE_CHARGE: Rule.EXACT_MATCH,
            Fields.TAXABLE_VALUE: Rule.ROUNDING_DIFFERENCE,
            Fields.TOTAL_GST: Rule.ROUNDING_DIFFERENCE,
            Fields.CESS: Rule.ROUNDING_DIFFERENCE,
        },
    },
    {
        "match_status": MatchStatus.MISMATCH,
        "rule": {
            Fields.FISCAL_YEAR: Rule.EXACT_MATCH,
            # Fields.SUPPLIER_GSTIN: Rule.MISMATCH,
            Fields.BILL_NO: Rule.FUZZY_MATCH,
            Fields.PLACE_OF_SUPPLY: Rule.EXACT_MATCH,
            Fields.REVERSE_CHARGE: Rule.EXACT_MATCH,
            Fields.TAXABLE_VALUE: Rule.ROUNDING_DIFFERENCE,
            Fields.TOTAL_GST: Rule.ROUNDING_DIFFERENCE,
            Fields.CESS: Rule.ROUNDING_DIFFERENCE,
        },
    },
    {
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
    },
    {
        "match_status": MatchStatus.RESIDUAL_MATCH,
        "rule": {
            Fields.FISCAL_YEAR: Rule.EXACT_MATCH,
            # Fields.SUPPLIER_GSTIN: Rule.MISMATCH,
            # Fields.BILL_NO: Rule.MISMATCH,
            Fields.PLACE_OF_SUPPLY: Rule.EXACT_MATCH,
            Fields.REVERSE_CHARGE: Rule.EXACT_MATCH,
            Fields.TAXABLE_VALUE: Rule.ROUNDING_DIFFERENCE,
            Fields.TOTAL_GST: Rule.ROUNDING_DIFFERENCE,
            Fields.CESS: Rule.ROUNDING_DIFFERENCE,
        },
    },
)


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
            query.where(IfNull(self.GSTR2.match_status, "") == "")
            .where(self.GSTR2.classification.isin(categories))
            .run(as_dict=True)
        )

        for doc in data:
            doc.fy = BaseUtil.get_fy(doc.bill_date)

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
            .where(IfNull(self.GSTR2.match_status, "") != "Amended")
            .groupby(self.GSTR2_ITEM.parent)
            .select(*fields, ConstantColumn("GST Inward Supply").as_("doctype"))
        )
        if self.include_ignored == 0:
            query = query.where(IfNull(self.GSTR2.action, "") != "Ignore")

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
            .where(self.PI.gst_category.isin(gst_category))
            .where(self.PI.is_return == is_return)
        )

        data = query.run(as_dict=True)

        for doc in data:
            doc.fy = BaseUtil.get_fy(doc.bill_date or doc.posting_date)

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

        query = (
            frappe.qb.from_(self.PI)
            .left_join(self.PI_TAX)
            .on(self.PI_TAX.parent == self.PI.name)
            .left_join(pi_item)
            .on(pi_item.parent == self.PI.name)
            .where(self.company_gstin == self.PI.company_gstin)
            .where(self.PI.docstatus == 1)
            .where(IfNull(self.PI.reconciliation_status, "") != "Not Applicable")
            .groupby(self.PI.name)
            .select(
                *fields,
                pi_item.taxable_value,
                ConstantColumn("Purchase Invoice").as_("doctype"),
            )
        )

        if self.include_ignored == 0:
            query = query.where(IfNull(self.PI.reconciliation_status, "") != "Ignored")

        return query

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
            fields += [
                # Default to posting date if bill date is not available.
                Case()
                .when(
                    IfNull(self.PI.bill_date, "") == "",
                    self.PI.posting_date,
                )
                .else_(self.PI.bill_date)
                .as_("bill_date")
            ]

        if additional_fields:
            fields += additional_fields

        return fields

    def query_tax_amount(self, account):
        account = get_escaped_name(account)
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


class BillOfEntry:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

        self.BOE = frappe.qb.DocType("Bill of Entry")
        self.BOE_TAX = frappe.qb.DocType("Bill of Entry Taxes")
        self.PI = frappe.qb.DocType("Purchase Invoice")

    def get_all(self, additional_fields=None, names=None, only_names=False):
        query = self.get_query(additional_fields)

        if only_names and not names:
            return

        elif only_names:
            query = query.where(self.BOE.name.isin(names))

        elif names:
            query = query.where(
                (self.BOE.posting_date[self.from_date : self.to_date])
                | (self.BOE.name.isin(names))
            )

        else:
            query = query.where(self.BOE.posting_date[self.from_date : self.to_date])

        return query.run(as_dict=True)

    def get_unmatched(self, category):
        gst_category = "SEZ" if category == "IMPGSEZ" else "Overseas"

        query = (
            self.get_query()
            .where(self.PI.gst_category == gst_category)
            .where(self.BOE.posting_date[self.from_date : self.to_date])
            .where(
                self.BOE.name.notin(
                    BillOfEntry.query_matched_bill_of_entry(
                        self.from_date, self.to_date
                    )
                )
            )
        )

        data = query.run(as_dict=True)

        for doc in data:
            doc.fy = BaseUtil.get_fy(doc.bill_date or doc.posting_date)

        return BaseUtil.get_dict_for_key("supplier_gstin", data)

    def get_query(self, additional_fields=None):
        fields = self.get_fields(additional_fields)

        query = (
            frappe.qb.from_(self.BOE)
            .left_join(self.BOE_TAX)
            .on(self.BOE_TAX.parent == self.BOE.name)
            .join(self.PI)
            .on(self.BOE.purchase_invoice == self.PI.name)
            .where(self.BOE.docstatus == 1)
            .groupby(self.BOE.name)
            .select(*fields, ConstantColumn("Bill of Entry").as_("doctype"))
        )

        if self.include_ignored == 0:
            query = query.where(IfNull(self.BOE.reconciliation_status, "") != "Ignored")

        return query

    def get_fields(self, additional_fields=None):
        gst_accounts = get_gst_accounts_by_type(self.company, "Input")
        tax_fields = [
            self.query_tax_amount(account).as_(tax[:-8])
            for tax, account in gst_accounts.items()
            if account
        ]

        fields = [
            self.BOE.name,
            self.BOE.bill_of_entry_no.as_("bill_no"),
            self.BOE.total_taxable_value.as_("taxable_value"),
            self.BOE.bill_of_entry_date.as_("bill_date"),
            self.BOE.posting_date,
            self.PI.supplier_name,
            self.PI.place_of_supply,
            self.PI.is_reverse_charge,
            *tax_fields,
        ]

        # In IMPGSEZ supplier details are avaialble in 2A
        purchase_fields = [
            "supplier_gstin",
            "gst_category",
        ]

        for field in purchase_fields:
            fields.append(
                Case()
                .when(self.PI.gst_category == "SEZ", getattr(self.PI, field))
                .else_(None)
                .as_(field)
            )

        # Add only boe fields
        if additional_fields:
            boe_fields = frappe.db.get_table_columns("Bill of Entry")
            for field in additional_fields:
                if field in boe_fields:
                    fields.append(getattr(self.BOE, field))

        return fields

    def query_tax_amount(self, account):
        account = get_escaped_name(account)
        return Abs(
            Sum(
                Case()
                .when(
                    self.BOE_TAX.account_head == account,
                    self.BOE_TAX.tax_amount,
                )
                .else_(0)
            )
        )

    @staticmethod
    def query_matched_bill_of_entry(from_date=None, to_date=None):
        GSTR2 = frappe.qb.DocType("GST Inward Supply")
        BOE = frappe.qb.DocType("Bill of Entry")

        query = (
            frappe.qb.from_(GSTR2)
            .select("link_name")
            .where(GSTR2.link_doctype == "Bill of Entry")
            .join(BOE)
            .on(BOE.name == GSTR2.link_name)
        )

        if from_date and to_date:
            query = query.where(BOE.posting_date[from_date:to_date])

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
            include_ignored=self.include_ignored,
        ).get_all(additional_fields, names, only_names)

    def get_unmatched_inward_supply(self, category, amended_category):
        return InwardSupply(
            company_gstin=self.company_gstin,
            from_date=self.inward_supply_from_date,
            to_date=self.inward_supply_to_date,
            gst_return=self.gst_return,
            include_ignored=self.include_ignored,
        ).get_unmatched(category, amended_category)

    def query_inward_supply(self, additional_fields=None):
        query = InwardSupply(
            company_gstin=self.company_gstin,
            from_date=self.inward_supply_from_date,
            to_date=self.inward_supply_to_date,
            gst_return=self.gst_return,
            include_ignored=self.include_ignored,
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
            include_ignored=self.include_ignored,
        ).get_all(additional_fields, names, only_names)

    def get_unmatched_purchase(self, category):
        return PurchaseInvoice(
            company=self.company,
            company_gstin=self.company_gstin,
            from_date=self.purchase_from_date,
            to_date=self.purchase_to_date,
            include_ignored=self.include_ignored,
        ).get_unmatched(category)

    def query_purchase_invoice(self, additional_fields=None):
        return PurchaseInvoice(
            company=self.company,
            company_gstin=self.company_gstin,
            include_ignored=self.include_ignored,
        ).get_query(additional_fields)

    def get_all_bill_of_entry(
        self, additional_fields=None, names=None, only_names=False
    ):
        return BillOfEntry(
            company=self.company,
            company_gstin=self.company_gstin,
            from_date=self.purchase_from_date,
            to_date=self.purchase_to_date,
            include_ignored=self.include_ignored,
        ).get_all(additional_fields, names, only_names)

    def get_unmatched_bill_of_entry(self, category):
        return BillOfEntry(
            company=self.company,
            company_gstin=self.company_gstin,
            from_date=self.purchase_from_date,
            to_date=self.purchase_to_date,
            include_ignored=self.include_ignored,
        ).get_unmatched(category)

    def query_bill_of_entry(self, additional_fields=None):
        return BillOfEntry(
            company=self.company,
            company_gstin=self.company_gstin,
            include_ignored=self.include_ignored,
        ).get_query(additional_fields)

    def get_unmatched_purchase_or_bill_of_entry(self, category):
        """
        Returns dict of unmatched purchase and bill of entry data.
        """
        if category in IMPORT_CATEGORY:
            return self.get_unmatched_bill_of_entry(category)

        return self.get_unmatched_purchase(category)


class Reconciler(BaseReconciliation):
    def reconcile(self, category, amended_category):
        """
        Reconcile purchases and inward supplies for given category.
        """
        # GSTIN Level matching
        purchases = self.get_unmatched_purchase_or_bill_of_entry(category)
        inward_supplies = self.get_unmatched_inward_supply(category, amended_category)
        self.reconcile_for_rules(GSTIN_RULES, purchases, inward_supplies)

        # In case of IMPG GST in not available in 2A. So skip PAN level matching.
        if category == "IMPG":
            return

        # PAN Level matching
        purchases = self.get_pan_level_data(purchases)
        inward_supplies = self.get_pan_level_data(inward_supplies)
        self.reconcile_for_rules(PAN_RULES, purchases, inward_supplies)

    def reconcile_for_rules(self, rules, purchases, inward_supplies):
        if not (purchases and inward_supplies):
            return

        for rule in rules:
            self.reconcile_for_rule(
                purchases,
                inward_supplies,
                rule.get("match_status").value,
                rule.get("rule"),
            )

    def reconcile_for_rule(self, purchases, inward_supplies, match_status, rules):
        """
        Sequentially reconcile invoices as per rules list.
        - Reconciliation only done between invoices of same GSTIN.
        - Where a match is found, update Inward Supply and Purchase Invoice.
        """

        for supplier_gstin in purchases:
            if not inward_supplies.get(supplier_gstin):
                continue

            for purchase_invoice_name, purchase in (
                purchases[supplier_gstin].copy().items()
            ):
                for inward_supply_name, inward_supply in (
                    inward_supplies[supplier_gstin].copy().items()
                ):
                    if match_status == "Residual Match":
                        if (
                            abs((purchase.bill_date - inward_supply.bill_date).days)
                            > 10
                        ):
                            continue

                    if not self.is_doc_matching(purchase, inward_supply, rules):
                        continue

                    self.update_matching_doc(
                        match_status,
                        purchase.name,
                        inward_supply.name,
                        purchase.doctype,
                    )

                    # Remove from current data to ensure matching is done only once.
                    purchases[supplier_gstin].pop(purchase_invoice_name)
                    inward_supplies[supplier_gstin].pop(inward_supply_name)
                    break

    def is_doc_matching(self, purchase, inward_supply, rules):
        """
        Returns true if all fields match from purchase and inward supply as per rules.

        param purchase: purchase doc
        param inward_supply: inward supply doc
        param rules: dict of rule against field to match
        """

        for field, rule in rules.items():
            if not self.is_field_matching(purchase, inward_supply, field.value, rule):
                return False

        return True

    def is_field_matching(self, purchase, inward_supply, field, rule):
        """
        Returns true if the field matches from purchase and inward supply as per the rule.

        param purchase: purchase doc
        param inward_supply: inward supply doc
        param field: field to match
        param rule: rule applied to match
        """

        if rule == Rule.EXACT_MATCH:
            return purchase[field] == inward_supply[field]
        elif rule == Rule.FUZZY_MATCH:
            return self.fuzzy_match(purchase, inward_supply)
        elif rule == Rule.ROUNDING_DIFFERENCE:
            return self.get_amount_difference(purchase, inward_supply, field) <= 1

    def fuzzy_match(self, purchase, inward_supply):
        """
        Returns true if the (cleaned) bill_no approximately match.
        - For a fuzzy match, month of invoice and inward supply should be same.
        - First check for partial ratio, with 100% confidence
        - Next check for approximate match, with 90% confidence
        """
        if not purchase.bill_no or not inward_supply.bill_no:
            return False

        if abs((purchase.bill_date - inward_supply.bill_date).days) > 10:
            return False

        if not purchase._bill_no:
            purchase._bill_no = BaseUtil.get_cleaner_bill_no(
                purchase.bill_no, purchase.fy
            )

        if not inward_supply._bill_no:
            inward_supply._bill_no = BaseUtil.get_cleaner_bill_no(
                inward_supply.bill_no, inward_supply.fy
            )

        partial_ratio = fuzz.partial_ratio(purchase._bill_no, inward_supply._bill_no)
        if float(partial_ratio) == 100:
            return True

        return (
            float(process.extractOne(purchase._bill_no, [inward_supply._bill_no])[1])
            >= 90.0
        )

    def get_amount_difference(self, purchase, inward_supply, field):
        if field == "cess":
            BaseUtil.update_cess_amount(purchase)

        if field == "total_gst":
            BaseUtil.update_total_gst_amount(purchase)
            BaseUtil.update_total_gst_amount(inward_supply)

        return abs(purchase.get(field, 0) - inward_supply.get(field, 0))

    def update_matching_doc(
        self, match_status, purchase_invoice_name, inward_supply_name, link_doctype
    ):
        """Update matching doc for records."""

        if match_status == "Residual Match":
            match_status = "Mismatch"

        inward_supply_fields = {
            "match_status": match_status,
            "link_doctype": link_doctype,
            "link_name": purchase_invoice_name,
        }

        frappe.db.set_value(
            "GST Inward Supply", inward_supply_name, inward_supply_fields
        )

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

            purchase.bill_date = format_date(purchase.bill_date)
            inward_supply.bill_date = format_date(inward_supply.bill_date)

            doc.update(purchase)
            doc.update(
                {f"{prefix}_{key}": value for key, value in inward_supply.items()}
            )
            if doc.supplier_gstin:
                doc.pan = doc.supplier_gstin[2:-3]

        return data

    def get_manually_matched_data(self, purchase_name: str, inward_supply_name: str):
        """
        Get manually matched data for given purchase invoice and inward supply.
        This can be used to show comparision of matched values.
        """
        inward_supplies = self.get_all_inward_supply(
            names=[inward_supply_name], only_names=True
        )
        purchases = self.get_all_purchase_invoice_and_bill_of_entry(
            "", [purchase_name], only_names=True
        )

        reconciliation_data = [
            frappe._dict(
                {
                    "_inward_supply": (
                        inward_supplies[0] if inward_supplies else frappe._dict()
                    ),
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

        inward_supplies = self.get_all_inward_supply(
            names=inward_supply_names, only_names=only_names
        )
        purchases_and_bill_of_entry = self.get_all_purchase_invoice_and_bill_of_entry(
            inward_supplies, purchase_names, only_names
        )

        reconciliation_data = []
        for doc in inward_supplies:
            reconciliation_data.append(
                frappe._dict(
                    {
                        "_inward_supply": doc,
                        "_purchase_invoice": purchases_and_bill_of_entry.pop(
                            doc.link_name, frappe._dict()
                        ),
                    }
                )
            )

        for doc in purchases_and_bill_of_entry.values():
            reconciliation_data.append(frappe._dict({"_purchase_invoice": doc}))

        self.process_data(reconciliation_data, retain_doc=retain_doc)
        return reconciliation_data

    def get_all_inward_supply(
        self, additional_fields=None, names=None, only_names=False
    ):
        inward_supply_fields = [
            "supplier_name",
            "classification",
            "match_status",
            "action",
            "link_doctype",
            "link_name",
        ]

        return (
            super().get_all_inward_supply(inward_supply_fields, names, only_names) or []
        )

    def get_all_purchase_invoice_and_bill_of_entry(
        self, inward_supplies, purchase_names, only_names=False
    ):
        purchase_fields = [
            "supplier",
            "supplier_name",
            "is_return",
            "gst_category",
            "reconciliation_status",
        ]

        boe_names = purchase_names

        if not only_names:
            purchase_names = set()
            boe_names = set()
            for doc in inward_supplies:
                if doc.link_doctype == "Purchase Invoice":
                    purchase_names.add(doc.link_name)

                elif doc.link_doctype == "Bill of Entry":
                    boe_names.add(doc.link_name)

        purchases = (
            super().get_all_purchase_invoice(
                purchase_fields, purchase_names, only_names
            )
            or []
        )

        bill_of_entries = (
            super().get_all_bill_of_entry(purchase_fields, boe_names, only_names) or []
        )

        if not purchases and not bill_of_entries:
            return {}

        purchases.extend(bill_of_entries)

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

            if retain_doc and purchase:
                BaseUtil.update_cess_amount(purchase)

    def update_fields(self, data, purchase, inward_supply):
        for field in ("supplier_name", "supplier_gstin", "bill_no", "bill_date"):
            data[field] = purchase.get(field) or inward_supply.get(field)

        data.update(
            {
                "supplier_name": data.supplier_name
                or self.guess_supplier_name(data.supplier_gstin),
                "supplier_gstin": data.supplier_gstin or data.supplier_name,
                "purchase_doctype": purchase.get("doctype"),
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
                "Ignore"
                if purchase.get("reconciliation_status") == "Ignored"
                else "No Action"
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

        if not classification and doc.get("doctype") == "Bill of Entry":
            classification = "IMPG"

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
    def get_dict_for_key(key, args_list):
        new_dict = frappe._dict()
        for data in args_list:
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
        if doc.get("cess_non_advol"):
            doc.cess = doc.get("cess", 0) + doc.get("cess_non_advol", 0)
            doc.cess_non_advol = 0

    @staticmethod
    def update_total_gst_amount(doc):
        if not doc.get("total_gst"):
            doc.total_gst = doc.cgst + doc.sgst + doc.igst

    @staticmethod
    def get_periods(date_range, return_type: ReturnType, reversed_order=False):
        """Returns a list of month (formatted as `MMYYYY`) in a fiscal year"""
        if not date_range:
            return []

        date_range = (getdate(date_range[0]), getdate(date_range[1]))
        end_date = min(date_range[1], BaseUtil._getdate(return_type))

        # latest to oldest
        return tuple(
            BaseUtil._reversed(
                BaseUtil._get_periods(date_range[0], end_date), reversed_order
            )
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
