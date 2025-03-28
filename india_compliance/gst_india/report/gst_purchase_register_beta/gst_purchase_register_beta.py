# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt
import frappe
from frappe import _
from frappe.query_builder import Case
from frappe.query_builder.custom import ConstantColumn
from frappe.query_builder.functions import Ifnull, IfNull, LiteralValue, Sum

from india_compliance.gst_india.constants import GST_TAX_TYPES
from india_compliance.gst_india.overrides.transaction import is_inter_state_supply

SECTION_MAPPING = {
    "4": {
        "ITC Available": [
            "Import Of Goods",
            "Import Of Service",
            "ITC on Reverse Charge",
            "Input Service Distributor",
            "All Other ITC",
        ],
        "ITC Reversed": [
            "As per rules 42 & 43 of CGST Rules and section 17(5)",
            "Others",
        ],
        "Ineligible ITC": [
            "Reclaim of ITC Reversal",
            "ITC restricted due to PoS rules",
        ],
    },
    "5": {
        "Composition Scheme, Exempted, Nil Rated": [
            "Composition Scheme, Exempted, Nil Rated",
        ],
        "Non-GST": ["Non-GST"],
    },
}


AMOUNT_FIELDS_MAP = {
    "4": {
        "igst_amount": 0,
        "cgst_amount": 0,
        "sgst_amount": 0,
        "cess_amount": 0,
    },
    "5": {
        "intra": 0,
        "inter": 0,
    },
}


def execute(filters: dict | None = None):
    if filters.sub_section == "4":
        report = GSTR3B_ITC_Details(frappe._dict(filters or {}))

    elif filters.sub_section == "5":
        report = GSTR3B_Inward_Nil_Exempt(frappe._dict(filters or {}))

    return report.run()


class BaseGSTR3B:
    def __init__(self, filters=None):
        self.filters = filters
        self.data = []
        self.company = self.filters.company
        self.company_gstin = self.filters.company_gstin
        self.company_currency = frappe.get_cached_value(
            "Company", filters.get("company"), "default_currency"
        )
        self.sub_section = self.filters.sub_section
        self.AMOUNT_FIELDS = AMOUNT_FIELDS_MAP[self.sub_section]
        self.from_date = self.filters.get("date_range")[0]
        self.to_date = self.filters.get("date_range")[1]
        self.group_by = self.filters.summary_by != "Summary by Item"

        self.initialize_columns()

    def initialize_columns(self):
        if self.filters.summary_by == "Overview":
            self.columns = [
                {
                    "label": _("Description"),
                    "fieldname": "description",
                    "width": "400",
                },
                {
                    "label": _("No. of records"),
                    "fieldname": "no_of_records",
                    "width": "120",
                    "fieldtype": "Int",
                },
            ]
        else:
            self.columns = [
                {
                    "fieldname": "voucher_type",
                    "label": _("Voucher Type"),
                    "fieldtype": "Data",
                    "width": 200,
                },
                {
                    "fieldname": "voucher_no",
                    "label": _("Voucher No"),
                    "fieldtype": "Dynamic Link",
                    "options": "voucher_type",
                    "width": 200,
                },
                {
                    "fieldname": "posting_date",
                    "label": _("Posting Date"),
                    "fieldtype": "Date",
                    "width": 150,
                },
            ]

    def run(self):
        self.get_data()
        self.extend_columns()

        return self.columns, self.data

    def extend_columns(self):
        raise NotImplementedError("Report Not Available")

    def get_data(self):
        raise NotImplementedError("Report Not Available")

    def select_item_details(self, query, doc_item):
        return query.select(
            doc_item.item_code,
            doc_item.gst_hsn_code,
            (doc_item.cgst_rate + doc_item.sgst_rate + doc_item.igst_rate).as_(
                "gst_rate"
            ),
            doc_item.taxable_value,
            doc_item.cgst_amount,
            doc_item.sgst_amount,
            doc_item.igst_amount,
            (doc_item.cess_amount + doc_item.cess_non_advol_amount).as_("cess_amount"),
            (
                doc_item.cgst_amount
                + doc_item.sgst_amount
                + doc_item.igst_amount
                + doc_item.cess_amount
                + doc_item.cess_non_advol_amount
            ).as_("total_tax"),
            (
                doc_item.taxable_value
                + doc_item.cgst_amount
                + doc_item.sgst_amount
                + doc_item.igst_amount
                + doc_item.cess_amount
                + doc_item.cess_non_advol_amount
            ).as_("total_amount"),
        )

    def select_tax_details(self, query, doc_item):
        return query.select(
            Sum(doc_item.igst_amount).as_("igst_amount"),
            Sum(doc_item.cgst_amount).as_("cgst_amount"),
            Sum(doc_item.sgst_amount).as_("sgst_amount"),
            Sum(doc_item.cess_amount + doc_item.cess_non_advol_amount).as_(
                "cess_amount"
            ),
            Sum(
                doc_item.igst_amount
                + doc_item.cgst_amount
                + doc_item.sgst_amount
                + doc_item.cess_amount
                + doc_item.cess_non_advol_amount
            ).as_("total_tax"),
            Sum(
                doc_item.taxable_value
                + doc_item.igst_amount
                + doc_item.cgst_amount
                + doc_item.sgst_amount
                + doc_item.cess_amount
                + doc_item.cess_non_advol_amount
            ).as_("total_amount"),
            Sum(doc_item.taxable_value).as_("taxable_value"),
        )

    def get_common_filters(self, query, doc):
        return query.where(
            (doc.docstatus == 1)
            & (doc.posting_date[self.from_date : self.to_date])
            & (doc.company == self.company)
            & (doc.company_gstin == self.company_gstin)
        )

    def get_sub_categories(self, category):
        return SECTION_MAPPING[self.sub_section][category]

    def filter_by_category(self, category, sub_category):
        if (
            self.filters.get("invoice_sub_category")
            and self.filters.invoice_sub_category != sub_category
        ):
            return True

        if (
            self.filters.get("invoice_category")
            and self.filters.invoice_category != category
        ):
            return True

    def get_tax_columns(self):
        return [
            {
                "fieldname": "taxable_value",
                "label": _("Taxable Value"),
                "fieldtype": "Currency",
                "width": 90,
            },
            {
                "fieldname": "cgst_amount",
                "label": _("CGST Amount"),
                "fieldtype": "Currency",
                "width": 90,
            },
            {
                "fieldname": "sgst_amount",
                "label": _("SGST Amount"),
                "fieldtype": "Currency",
                "width": 90,
            },
            {
                "fieldname": "igst_amount",
                "label": _("IGST Amount"),
                "fieldtype": "Currency",
                "width": 90,
            },
            {
                "fieldname": "cess_amount",
                "label": _("CESS Amount"),
                "fieldtype": "Currency",
                "width": 90,
            },
            {
                "fieldname": "total_tax",
                "label": _("Total Tax"),
                "fieldtype": "Currency",
                "width": 90,
            },
            {
                "fieldname": "total_amount",
                "label": _("Total Amount"),
                "fieldtype": "Currency",
                "width": 90,
            },
        ]

    def get_item_wise_columns(self):
        self.columns.extend(
            [
                {
                    "fieldname": "item_code",
                    "label": _("Item Code"),
                    "fieldtype": "Link",
                    "options": "Item",
                    "width": 180,
                },
                {
                    "fieldname": "gst_hsn_code",
                    "label": _("HSN Code"),
                    "fieldtype": "Link",
                    "options": "GST HSN Code",
                    "width": 120,
                },
                {
                    "fieldname": "gst_rate",
                    "label": _("GST Rate"),
                    "fieldtype": "Percent",
                    "width": 90,
                },
                *self.get_tax_columns(),
            ]
        )

    def create_tree_view(self):
        mapping = SECTION_MAPPING[self.filters.sub_section]

        final_summary = []
        sub_category_summary = self.get_sub_category_summary(mapping)

        for category, sub_categories in mapping.items():
            if category == "Ineligible ITC" and self.filters.sub_section == "4":
                self.add_net_itc_row(final_summary)

            category_summary = {
                "description": category,
                "no_of_records": 0,
                "indent": 0,
                **self.AMOUNT_FIELDS,
            }
            final_summary.append(category_summary)

            for sub_category in sub_categories:
                sub_category_row = sub_category_summary[sub_category]
                category_summary["no_of_records"] += sub_category_row["no_of_records"]

                for key in self.AMOUNT_FIELDS:
                    category_summary[key] += sub_category_row[key]

                final_summary.append(sub_category_row)

        self.data = final_summary

    def add_net_itc_row(self, summary):
        row = {
            "description": "Net ITC Avaliable",
            "no_of_records": 0,
            "indent": 0,
            **self.AMOUNT_FIELDS,
        }

        for summary_row in summary:
            if summary_row["description"] == "ITC Available":
                for key in self.AMOUNT_FIELDS:
                    row[key] += summary_row[key]

                row["no_of_records"] += summary_row["no_of_records"]
            elif summary_row["description"] == "ITC Reversed":
                for key in self.AMOUNT_FIELDS:
                    row[key] -= summary_row[key]

                row["no_of_records"] -= summary_row["no_of_records"]

        summary.append(row)

    def get_sub_category_summary(self, mapping):
        sub_categories = []
        for category in mapping:
            sub_categories.extend(mapping[category])

        summary = {
            category: {
                "description": category,
                "no_of_records": 0,
                "indent": 1,
                "unique_records": set(),
                **self.AMOUNT_FIELDS,
            }
            for category in sub_categories
        }

        def _update_summary_row(row, sub_category_field="invoice_sub_category"):
            if row.get(sub_category_field) not in sub_categories:
                return

            summary_row = summary[row.get(sub_category_field)]

            for key in self.AMOUNT_FIELDS:
                summary_row[key] += row[key]

            summary_row["unique_records"].add(row["voucher_no"])

        for row in self.data:
            _update_summary_row(row)

        for summary_row in summary.values():
            summary_row["no_of_records"] = len(summary_row["unique_records"])

        return summary


class GSTR3B_ITC_Details(BaseGSTR3B):
    def extend_columns(self):
        if self.filters.summary_by == "Summary by Item":
            self.get_item_wise_columns()
        elif self.filters.summary_by == "Overview":
            self.columns.extend(
                [
                    {
                        "fieldname": "igst_amount",
                        "label": _("Integrated Tax"),
                        "fieldtype": "Currency",
                        "options": self.company_currency,
                        "width": 120,
                    },
                    {
                        "fieldname": "cgst_amount",
                        "label": _("Central Tax"),
                        "fieldtype": "Currency",
                        "options": self.company_currency,
                        "width": 120,
                    },
                    {
                        "fieldname": "sgst_amount",
                        "label": _("State/UT Tax"),
                        "fieldtype": "Currency",
                        "options": self.company_currency,
                        "width": 120,
                    },
                    {
                        "fieldname": "cess_amount",
                        "label": _("Cess Tax"),
                        "fieldtype": "Currency",
                        "options": self.company_currency,
                        "width": 120,
                    },
                ]
            )
        else:
            self.columns.extend(
                [
                    {
                        "fieldname": "gst_category",
                        "label": _("GST Category"),
                        "fieldtype": "Data",
                        "width": 150,
                    },
                    *self.get_tax_columns(),
                ]
            )

        self.columns.append(
            {
                "fieldname": "invoice_sub_category",
                "label": _("Invoice Sub Category"),
                "fieldtype": "Data",
                "width": 200,
                "hidden": self.filters.get("summary_by") == "Overview",
            },
        )

    def get_data(self):
        self.get_invoice_data()
        if self.filters.summary_by == "Overview":
            self.create_tree_view()

    def get_invoice_data(self):
        purchase_data = self.get_itc_from_purchase()
        boe_data = self.get_itc_from_boe()
        journal_entry_data = self.get_itc_from_journal_entry()
        reversal_us_17_4 = self.get_itc_reversal_us_17_5()
        ineligible_itc = self.get_ineligible_itc()

        data = (
            purchase_data
            + boe_data
            + journal_entry_data
            + reversal_us_17_4
            + ineligible_itc
        )

        self.data = sorted(
            data,
            key=lambda k: (k["invoice_sub_category"], k["posting_date"]),
        )

    def get_itc_from_purchase(self):
        purchase_invoice = frappe.qb.DocType("Purchase Invoice")
        purchase_invoice_item = frappe.qb.DocType("Purchase Invoice Item")

        query = (
            frappe.qb.from_(purchase_invoice)
            .inner_join(purchase_invoice_item)
            .on(purchase_invoice_item.parent == purchase_invoice.name)
            .select(
                ConstantColumn("Purchase Invoice").as_("voucher_type"),
                purchase_invoice.name.as_("voucher_no"),
                purchase_invoice.posting_date,
                purchase_invoice.itc_classification.as_("invoice_sub_category"),
            )
            .where(
                (purchase_invoice.is_opening == "No")
                & (
                    purchase_invoice.company_gstin
                    != Ifnull(purchase_invoice.supplier_gstin, "")
                )
                & (Ifnull(purchase_invoice.itc_classification, "") != "")
                & (
                    IfNull(purchase_invoice.ineligibility_reason, "")
                    != "ITC restricted due to PoS rules"
                )
            )
        )

        query = self.get_common_filters(query, purchase_invoice)

        if self.group_by:
            query = self.select_tax_details(query, purchase_invoice_item)
            query = query.select(
                IfNull(purchase_invoice.gst_category, "").as_("gst_category"),
            ).groupby(purchase_invoice.name)
        else:
            query = self.select_item_details(query, purchase_invoice_item)

        if self.filters.get("invoice_sub_category"):
            query = query.where(
                purchase_invoice.itc_classification == self.filters.invoice_sub_category
            )

        if self.filters.get("invoice_category"):
            query = query.where(
                purchase_invoice.itc_classification.isin(
                    self.get_sub_categories(self.filters.invoice_category)
                )
            )

        return query.run(as_dict=True)

    def get_itc_from_boe(self):
        if self.filter_by_category("ITC Available", "Import Of Goods"):
            return []

        boe = frappe.qb.DocType("Bill of Entry")
        boe_item = frappe.qb.DocType("Bill of Entry Item")

        query = (
            frappe.qb.from_(boe)
            .inner_join(boe_item)
            .on(boe_item.parent == boe.name)
            .select(
                ConstantColumn("Bill of Entry").as_("voucher_type"),
                boe.name.as_("voucher_no"),
                boe.posting_date,
                ConstantColumn("Import Of Goods").as_("invoice_sub_category"),
            )
        )

        if self.group_by:
            query = self.select_tax_details(query, boe_item)
            query = query.select(
                LiteralValue(0).as_("cgst_amount"),
                LiteralValue(0).as_("sgst_amount"),
            ).groupby(boe.name)

        else:
            query = self.select_item_details(query, boe_item)

        query = self.get_common_filters(query, boe)

        return query.run(as_dict=True)

    def get_itc_from_journal_entry(self):
        if self.filter_by_category(
            "ITC Reversed", "As per rules 42 & 43 of CGST Rules and section 17(5)"
        ):
            return []

        journal_entry = frappe.qb.DocType("Journal Entry")

        query = (
            IneligibleITC(self.filters)
            .get_common_query_for_journal_entry()
            .select(
                ConstantColumn(
                    "As per rules 42 & 43 of CGST Rules and section 17(5)"
                ).as_("invoice_sub_category")
            )
            .where(journal_entry.voucher_type == "Reversal of ITC")
        )

        return query.run(as_dict=True)

    def get_itc_reversal_us_17_5(self):
        ineligible_itc = IneligibleITC(self.filters)
        return (
            ineligible_itc.get_for_purchase("Ineligible As Per Section 17(5)")
            + ineligible_itc.get_for_bill_of_entry()
        )

    def get_ineligible_itc(self):
        ineligible_itc = IneligibleITC(self.filters)
        return (
            ineligible_itc.get_for_purchase("ITC restricted due to PoS rules")
            + ineligible_itc.get_reclaim_of_itc_reversal()
        )


class GSTR3B_Inward_Nil_Exempt(BaseGSTR3B):
    def extend_columns(self):
        if self.filters.summary_by == "Summary by Item":
            self.get_item_wise_columns()
        elif self.filters.summary_by == "Overview":
            self.columns.extend(
                [
                    {
                        "fieldname": "intra",
                        "label": _("Intra State"),
                        "fieldtype": "Currency",
                        "options": self.company_currency,
                        "width": 120,
                    },
                    {
                        "fieldname": "inter",
                        "label": _("Inter State"),
                        "fieldtype": "Currency",
                        "options": self.company_currency,
                        "width": 120,
                    },
                ]
            )
        else:
            self.columns.extend(
                [
                    {
                        "fieldname": "gst_category",
                        "label": _("GST Category"),
                        "fieldtype": "Data",
                        "width": 150,
                    },
                    *self.get_tax_columns(),
                ]
            )

        self.columns.extend(
            [
                {
                    "fieldname": "invoice_type",
                    "label": _("Invoice Type"),
                    "fieldtype": "Data",
                    "width": 200,
                    "hidden": self.filters.get("summary_by") == "Overview",
                },
                {
                    "fieldname": "invoice_sub_category",
                    "label": _("Invoice Sub Category"),
                    "fieldtype": "Data",
                    "width": 200,
                    "hidden": self.filters.get("summary_by") == "Overview",
                },
            ]
        )

    def get_data(self):
        formatted_data = []

        invoices = self.get_inward_nil_exempt()

        for invoice in invoices:
            invoice_sub_category = ""

            intra, inter = 0, 0
            taxable_value = invoice.taxable_value

            if (
                invoice.gst_treatment in ["Nil-Rated", "Exempted"]
                or invoice.get("gst_category") == "Registered Composition"
            ):
                invoice_sub_category = "Composition Scheme, Exempted, Nil Rated"

            elif invoice.gst_treatment == "Non-GST":
                invoice_sub_category = "Non GST Supply"

            # don't include invoice if not consistent with the filters applied
            if self.filter_by_category(invoice_sub_category, invoice_sub_category):
                continue

            if is_inter_state_supply(invoice):
                inter = taxable_value
            else:
                intra = taxable_value

            formatted_data.append(
                {
                    **invoice,
                    "intra": intra,
                    "inter": inter,
                    "invoice_sub_category": invoice_sub_category,
                    "invoice_type": "Inter State" if inter else "Intra State",
                }
            )

        self.data = sorted(
            formatted_data, key=lambda k: (k["invoice_sub_category"], k["posting_date"])
        )

        if self.filters.summary_by == "Overview":
            self.create_tree_view()

    def get_address_state_map(self):
        return frappe._dict(
            frappe.get_all("Address", fields=["name", "gst_state_number"], as_list=1)
        )

    def get_inward_nil_exempt(self):
        purchase_invoice = frappe.qb.DocType("Purchase Invoice")
        purchase_invoice_item = frappe.qb.DocType("Purchase Invoice Item")

        query = (
            frappe.qb.from_(purchase_invoice)
            .inner_join(purchase_invoice_item)
            .on(purchase_invoice_item.parent == purchase_invoice.name)
            .select(
                ConstantColumn("Purchase Invoice").as_("voucher_type"),
                purchase_invoice.name.as_("voucher_no"),
                purchase_invoice.posting_date,
                purchase_invoice.place_of_supply,
                purchase_invoice.supplier_address,
                purchase_invoice_item.gst_treatment,
                purchase_invoice.supplier_gstin,
                purchase_invoice.company_gstin,
                IfNull(purchase_invoice.gst_category, "").as_("gst_category"),
            )
            .where(
                (purchase_invoice.is_opening == "No")
                & (purchase_invoice.name == purchase_invoice_item.parent)
                & (
                    (purchase_invoice_item.gst_treatment != "Taxable")
                    | (purchase_invoice.gst_category == "Registered Composition")
                )
                & (
                    purchase_invoice.company_gstin
                    != IfNull(purchase_invoice.supplier_gstin, "")
                )
                & (purchase_invoice.gst_category != "Overseas")
            )
        )

        if self.group_by:
            query = query.select(
                Sum(purchase_invoice_item.taxable_value).as_("taxable_value"),
            ).groupby(purchase_invoice.name)

        else:
            query = self.select_item_details(query, purchase_invoice_item)

        query = self.get_common_filters(query, purchase_invoice)

        return query.run(as_dict=True)


class IneligibleITC:
    def __init__(self, filters) -> None:
        self.gstr3b = BaseGSTR3B(filters)

    def get_for_purchase(self, ineligibility_reason, group_by="name"):
        doctype = "Purchase Invoice"
        dt = frappe.qb.DocType(doctype)
        dt_item = frappe.qb.DocType(f"{doctype} Item")

        query = (
            self.get_common_query_for_purchase(doctype, dt, dt_item)
            .select(
                (dt.ineligibility_reason).as_("invoice_sub_category"),
                IfNull(dt.gst_category, "").as_("gst_category"),
            )
            .where((dt.is_opening == "No"))
            .where(IfNull(dt.ineligibility_reason, "") == ineligibility_reason)
            .groupby(dt[group_by])
        )

        if ineligibility_reason == "Ineligible As Per Section 17(5)":
            if self.gstr3b.filter_by_category(
                "ITC Reversed", "As per rules 42 & 43 of CGST Rules and section 17(5)"
            ):
                return []

            query = query.select(
                ConstantColumn(
                    "As per rules 42 & 43 of CGST Rules and section 17(5)"
                ).as_("invoice_sub_category")
            ).where(dt_item.is_ineligible_for_itc == 1)

        else:
            if self.gstr3b.filter_by_category("Ineligible ITC", ineligibility_reason):
                return []

        return query.run(as_dict=True)

    def get_for_bill_of_entry(self, group_by="name"):
        doctype = "Bill of Entry"
        dt = frappe.qb.DocType(doctype)
        dt_item = frappe.qb.DocType(f"{doctype} Item")
        query = (
            self.get_common_query_for_purchase(doctype, dt, dt_item)
            .select(
                ConstantColumn(
                    "As per rules 42 & 43 of CGST Rules and section 17(5)"
                ).as_("invoice_sub_category")
            )
            .where(dt_item.is_ineligible_for_itc == 1)
        )

        if self.gstr3b.filter_by_category(
            "ITC Reversed", "As per rules 42 & 43 of CGST Rules and section 17(5)"
        ):
            return []

        return query.groupby(dt[group_by]).run(as_dict=True)

    def get_reclaim_of_itc_reversal(self):
        if self.gstr3b.filter_by_category("Ineligible ITC", "Reclaim of ITC Reversal"):
            return []

        journal_entry = frappe.qb.DocType("Journal Entry")

        query = (
            self.get_common_query_for_journal_entry("debit")
            .select(
                journal_entry.voucher_type.as_("invoice_sub_category"),
            )
            .where(journal_entry.voucher_type == "Reclaim of ITC Reversal")
        )

        return query.run(as_dict=True)

    def get_common_query_for_purchase(self, doctype, dt, dt_item):
        query = (
            frappe.qb.from_(dt)
            .inner_join(dt_item)
            .on(dt.name == dt_item.parent)
            .select(
                ConstantColumn(doctype).as_("voucher_type"),
                dt.name.as_("voucher_no"),
                dt.posting_date,
            )
        )
        query = self.gstr3b.select_tax_details(query, dt_item)

        return self.gstr3b.get_common_filters(query, dt)

    def get_common_query_for_journal_entry(self, amount_key="credit"):
        journal_entry = frappe.qb.DocType("Journal Entry")
        journal_entry_account = frappe.qb.DocType("Journal Entry Account")

        query = (
            frappe.qb.from_(journal_entry)
            .inner_join(journal_entry_account)
            .on(journal_entry_account.parent == journal_entry.name)
            .select(
                ConstantColumn("Journal Entry").as_("voucher_type"),
                journal_entry.name.as_("voucher_no"),
                journal_entry.posting_date,
                *[
                    Sum(
                        Case()
                        .when(
                            journal_entry_account.gst_tax_type == tax,
                            (
                                getattr(
                                    journal_entry_account,
                                    f"{amount_key}_in_account_currency",
                                )
                            ),
                        )
                        .else_(0)
                    ).as_(f"{tax}_amount")
                    for tax in GST_TAX_TYPES[:-1]
                ],
                Sum(
                    Case()
                    .when(
                        journal_entry_account.gst_tax_type.isin(
                            ["cess", "cess_non_advol"]
                        ),
                        (
                            getattr(
                                journal_entry_account,
                                f"{amount_key}_in_account_currency",
                            )
                        ),
                    )
                    .else_(0)
                ).as_("cess_amount"),
                Sum(
                    Case()
                    .when(
                        journal_entry_account.gst_tax_type.isin(GST_TAX_TYPES),
                        (
                            getattr(
                                journal_entry_account,
                                f"{amount_key}_in_account_currency",
                            )
                        ),
                    )
                    .else_(0)
                ).as_("total_tax"),
                Sum(
                    Case()
                    .when(
                        journal_entry_account.gst_tax_type.isin(GST_TAX_TYPES),
                        (
                            getattr(
                                journal_entry_account,
                                f"{amount_key}_in_account_currency",
                            )
                        ),
                    )
                    .else_(0)
                ).as_("total_amount"),
            )
            .where(journal_entry.is_opening == "No")
            .groupby(journal_entry.name)
        )

        return self.gstr3b.get_common_filters(query, journal_entry)
