import frappe
from frappe.query_builder import Case
from frappe.query_builder.custom import ConstantColumn
from frappe.query_builder.functions import IfNull, Sum

from india_compliance.gst_india.constants import GST_TAX_TYPES, SERVICE_HSN_PREFIX
from india_compliance.gst_india.overrides.transaction import is_inter_state_supply
from india_compliance.gst_india.utils import get_full_gst_uom
from india_compliance.gst_india.utils.gstr_1 import GSTR1_SubCategory
from india_compliance.gst_india.utils.itc_claim import (
    apply_period_filter as _apply_itc_period_filter,
)

PURCHASE_INVOICE_DOCTYPES = ("Purchase Invoice", "Bill of Entry", "Journal Entry")

ITC_AMOUNT_KEYS = {
    "iamt": "igst_amount",
    "camt": "cgst_amount",
    "samt": "sgst_amount",
    "csamt": "cess_amount",
}

INWARD_ITC_SECTION_MAP = {
    "Import Of Goods": ("itc_avl", "IMPG", 1),
    "Import Of Service": ("itc_avl", "IMPS", 1),
    "ITC on Reverse Charge": ("itc_avl", "ISRC", 1),
    "Input Service Distributor": ("itc_avl", "ISD", 1),
    "All Other ITC": ("itc_avl", "OTH", 1),
    "As per rules 42 & 43 of CGST Rules and section 17(5)": ("itc_rev", "RUL", -1),
    "Others": ("itc_rev", "OTH", -1),
    "Reclaim of ITC Reversal": ("itc_inelg", "RUL", 0),
    "ITC restricted due to PoS rules": ("itc_inelg", "OTH", 0),
}

INWARD_NIL_EXEMPT_SECTION_MAP = {
    "Composition Scheme, Exempted, Nil Rated": "GST",
    "Non-GST": "NONGST",
}

INWARD_SECTION_SUB_CATEGORY_MAP = {
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

INWARD_SECTION_DOCTYPES = {
    "4": PURCHASE_INVOICE_DOCTYPES,
    "5": ("Purchase Invoice",),
}

PURCHASE_CATEGORY_CONDITIONS = {
    "Composition Scheme, Exempted, Nil Rated": {
        "category": "is_composition_nil_rated_or_exempted",
        "sub_category": "set_for_composition_nil_rated_or_exempted",
    },
    "Non-GST": {
        "category": "is_non_gst",
        "sub_category": "set_for_non_gst",
    },
    "ITC Available": {
        "category": "is_itc_available",
        "sub_category": "set_for_itc_available",
    },
    "Ineligible ITC": {
        "category": "is_ineligible_itc",
        "sub_category": "set_for_ineligible_itc",
    },
    # keep always after ITC available
    "ITC Reversed": {
        "category": "is_itc_reversed",
        "sub_category": "set_for_itc_reversed",
    },
}

BOE_CATEGORY_CONDITIONS = {
    "ITC Available": {
        "category": "is_itc_available_for_boe",
        "sub_category": "set_for_itc_available_boe",
    },
    "ITC Reversed": {
        "category": "is_itc_reversed_for_boe",
        "sub_category": "set_for_itc_reversed",
    },
}

JE_CATEGORY_CONDITIONS = {
    "ITC Reversed": {
        "category": "is_itc_reversed_for_je",
        "sub_category": "set_for_itc_reversed",
    },
    "ITC Reclaimed": {
        "category": "is_itc_reclaimed",
        "sub_category": "set_for_itc_reclaimed",
    },
}

INWARD_DOCTYPE_CONDITION_MAP = {
    "Purchase Invoice": PURCHASE_CATEGORY_CONDITIONS,
    "Bill of Entry": BOE_CATEGORY_CONDITIONS,
    "Journal Entry": JE_CATEGORY_CONDITIONS,
}

AMOUNT_FIELDS = (
    "taxable_value",
    "igst_amount",
    "cgst_amount",
    "sgst_amount",
    "cess_amount",
    "total_tax",
    "total_amount",
    "inter",
    "intra",
)


class GSTR3BCategoryConditions:
    def is_composition_nil_rated_or_exempted(self, invoice):
        return (
            invoice.gst_treatment == "Nil-Rated"
            or invoice.gst_treatment == "Exempted"
            or invoice.gst_category == "Registered Composition"
        )

    def is_non_gst(self, invoice):
        return invoice.gst_treatment == "Non-GST"

    def is_itc_available(self, invoice):
        return invoice.ineligibility_reason != "ITC restricted due to PoS rules"

    def is_itc_reversed(self, invoice):
        return invoice.ineligibility_reason == "Ineligible As Per Section 17(5)"

    def is_ineligible_itc(self, invoice):
        return invoice.ineligibility_reason == "ITC restricted due to PoS rules"

    def is_itc_available_for_boe(self, invoice):
        return True

    def is_itc_reversed_for_boe(self, invoice):
        return invoice.is_ineligible_for_itc

    def is_itc_reversed_for_je(self, invoice):
        return invoice.ineligibility_type == "Reversal Of ITC"

    def is_itc_reclaimed(self, invoice):
        return invoice.ineligibility_type == "Reclaim of ITC Reversal"


class GSTR3BSubcategory(GSTR3BCategoryConditions):
    def set_for_composition_nil_rated_or_exempted(self, invoice):
        invoice.invoice_sub_category = "Composition Scheme, Exempted, Nil Rated"

    def set_for_non_gst(self, invoice):
        invoice.invoice_sub_category = "Non-GST"

    def set_for_itc_available(self, invoice):
        invoice.invoice_sub_category = invoice.itc_classification

    def set_for_itc_reversed(self, invoice):
        invoice.invoice_sub_category = (
            "Others"
            if invoice.ineligibility_reason == "Others"
            else ("As per rules 42 & 43 of CGST Rules and section 17(5)")
        )

    def set_for_ineligible_itc(self, invoice):
        invoice.invoice_sub_category = "ITC restricted due to PoS rules"

    def set_for_itc_available_boe(self, invoice):
        invoice.invoice_sub_category = "Import Of Goods"

    def set_for_itc_reclaimed(self, invoice):
        invoice.invoice_sub_category = "Reclaim of ITC Reversal"


class GSTR3BInwardQuery:
    def __init__(self, filters):
        self.PI = frappe.qb.DocType("Purchase Invoice")
        self.PI_ITEM = frappe.qb.DocType("Purchase Invoice Item")
        self.BOE = frappe.qb.DocType("Bill of Entry")
        self.BOE_ITEM = frappe.qb.DocType("Bill of Entry Item")
        self.JE = frappe.qb.DocType("Journal Entry")
        self.JE_ACCOUNT = frappe.qb.DocType("Journal Entry Account")
        self.filters = frappe._dict(filters or {})

    def apply_itc_period_filter(self, query, doc):
        return _apply_itc_period_filter(
            query,
            doc,
            self.filters.get("from_date"),
            self.filters.get("to_date"),
            filter_by=self.filters.get("filter_by"),
        )

    def get_base_purchase_query(self):
        query = (
            frappe.qb.from_(self.PI)
            .inner_join(self.PI_ITEM)
            .on(self.PI_ITEM.parent == self.PI.name)
            .select(
                ConstantColumn("Purchase Invoice").as_("voucher_type"),
                self.PI.name.as_("voucher_no"),
                self.PI.posting_date,
                self.PI.itc_classification,
                IfNull(self.PI.ineligibility_reason, "").as_("ineligibility_reason"),
                IfNull(self.PI.place_of_supply, "").as_("place_of_supply"),
                IfNull(self.PI.gst_category, "").as_("gst_category"),
                self.PI.company_gstin,
                IfNull(self.PI.supplier_gstin, "").as_("supplier_gstin"),
                self.PI.is_reverse_charge,
                self.PI_ITEM.item_code,
                IfNull(self.PI_ITEM.gst_treatment, "").as_("gst_treatment"),
                self.PI_ITEM.gst_hsn_code,
                self.PI_ITEM.uom,
                self.PI_ITEM.qty,
                (self.PI_ITEM.cgst_rate + self.PI_ITEM.sgst_rate + self.PI_ITEM.igst_rate).as_("gst_rate"),
                self.PI_ITEM.taxable_value,
                self.PI_ITEM.cgst_amount,
                self.PI_ITEM.sgst_amount,
                self.PI_ITEM.igst_amount,
                (self.PI_ITEM.cess_amount + self.PI_ITEM.cess_non_advol_amount).as_("cess_amount"),
                (
                    self.PI_ITEM.cgst_amount
                    + self.PI_ITEM.sgst_amount
                    + self.PI_ITEM.igst_amount
                    + self.PI_ITEM.cess_amount
                    + self.PI_ITEM.cess_non_advol_amount
                ).as_("total_tax"),
                (
                    self.PI_ITEM.taxable_value
                    + self.PI_ITEM.cgst_amount
                    + self.PI_ITEM.sgst_amount
                    + self.PI_ITEM.igst_amount
                    + self.PI_ITEM.cess_amount
                    + self.PI_ITEM.cess_non_advol_amount
                ).as_("total_amount"),
            )
            .where(self.PI.is_opening == "No")
            .where(self.PI.company_gstin != IfNull(self.PI.supplier_gstin, ""))
            .where(self.PI.is_boe_applicable == 0)
        )

        return self.get_query_with_common_filters(query, self.PI)

    def get_base_boe_query(self):
        query = (
            frappe.qb.from_(self.BOE)
            .inner_join(self.BOE_ITEM)
            .on(self.BOE_ITEM.parent == self.BOE.name)
            .select(
                ConstantColumn("Bill of Entry").as_("voucher_type"),
                self.BOE.name.as_("voucher_no"),
                self.BOE.posting_date,
                ConstantColumn("Import Of Goods").as_("itc_classification"),
                self.BOE.company_gstin,
                self.BOE_ITEM.is_ineligible_for_itc,
                self.BOE_ITEM.item_code,
                self.BOE_ITEM.gst_hsn_code,
                self.BOE_ITEM.uom,
                self.BOE_ITEM.qty,
                (self.BOE_ITEM.cgst_rate + self.BOE_ITEM.sgst_rate + self.BOE_ITEM.igst_rate).as_("gst_rate"),
                self.BOE_ITEM.taxable_value,
                self.BOE_ITEM.cgst_amount,
                self.BOE_ITEM.sgst_amount,
                self.BOE_ITEM.igst_amount,
                (self.BOE_ITEM.cess_amount + self.BOE_ITEM.cess_non_advol_amount).as_("cess_amount"),
                (
                    self.BOE_ITEM.cgst_amount
                    + self.BOE_ITEM.sgst_amount
                    + self.BOE_ITEM.igst_amount
                    + self.BOE_ITEM.cess_amount
                    + self.BOE_ITEM.cess_non_advol_amount
                ).as_("total_tax"),
                (
                    self.BOE_ITEM.taxable_value
                    + self.BOE_ITEM.cgst_amount
                    + self.BOE_ITEM.sgst_amount
                    + self.BOE_ITEM.igst_amount
                    + self.BOE_ITEM.cess_amount
                    + self.BOE_ITEM.cess_non_advol_amount
                ).as_("total_amount"),
            )
        )

        return self.get_query_with_common_filters(query, self.BOE)

    def get_base_je_query(self):
        key_field_map = {
            "cgst_amount": ["cgst"],
            "sgst_amount": ["sgst"],
            "igst_amount": ["igst"],
            "cess_amount": ["cess", "cess_non_advol"],
            "total_tax": GST_TAX_TYPES,
            "total_amount": GST_TAX_TYPES,
        }

        query = (
            frappe.qb.from_(self.JE)
            .inner_join(self.JE_ACCOUNT)
            .on(self.JE_ACCOUNT.parent == self.JE.name)
            .select(
                ConstantColumn("Journal Entry").as_("voucher_type"),
                self.JE.voucher_type.as_("ineligibility_type"),
                self.JE.name.as_("voucher_no"),
                self.JE.posting_date,
                IfNull(self.JE.ineligibility_reason, "").as_("ineligibility_reason"),
                *[
                    Sum(
                        Case()
                        .when(
                            self.JE_ACCOUNT.gst_tax_type.isin(fields),
                            Case()
                            .when(
                                self.JE.voucher_type == "Reversal Of ITC",
                                self.JE_ACCOUNT.credit_in_account_currency
                                - self.JE_ACCOUNT.debit_in_account_currency,
                            )
                            .else_(
                                self.JE_ACCOUNT.debit_in_account_currency
                                - self.JE_ACCOUNT.credit_in_account_currency
                            ),
                        )
                        .else_(0)
                    ).as_(key)
                    for key, fields in key_field_map.items()
                ],
            )
            .where(self.JE.is_opening == "No")
            .where(self.JE.voucher_type.isin(["Reclaim of ITC Reversal", "Reversal Of ITC"]))
            .groupby(self.JE.name)
        )

        return self.get_query_with_common_filters(query, self.JE)

    def get_query_with_common_filters(self, query, doc):
        """
        Apply common filters to the query.
        """
        query = query.where((doc.docstatus == 1) & (doc.company == self.filters.company))

        query = self.apply_itc_period_filter(query, doc)

        if self.filters.company_gstin:
            query = query.where(doc.company_gstin == self.filters.company_gstin)

        return query


class GSTR3BInwardInvoices(GSTR3BInwardQuery, GSTR3BSubcategory):
    def __init__(self, filters):
        super().__init__(filters)
        self.gst_settings = frappe.get_cached_doc("GST Settings")

    def get_all_data(self, group_by_invoice=False):
        """Return all inward invoices across all supported doctypes."""
        invoices = []
        for doctype in PURCHASE_INVOICE_DOCTYPES:
            invoices.extend(self.get_data(doctype))

        if not group_by_invoice:
            return invoices

        return self.get_invoice_wise_data(invoices)

    def get_section_data(self, sub_section, group_by_invoice=False, invoice_sub_categories=None):
        invoices = []

        for doctype in INWARD_SECTION_DOCTYPES.get(str(sub_section), ()):
            invoices.extend(self.get_data(doctype, group_by_invoice=group_by_invoice))

        return self.get_filtered_invoices(
            invoices,
            invoice_sub_categories or self.get_section_sub_categories(sub_section),
        )

    @classmethod
    def get_section_sub_categories(cls, sub_section):
        section = INWARD_SECTION_SUB_CATEGORY_MAP.get(str(sub_section), {})

        return [category for sub_categories in section.values() for category in sub_categories]

    def get_data(self, doctype, group_by_invoice=False):
        if doctype == "Purchase Invoice":
            query = self.get_base_purchase_query()
        elif doctype == "Bill of Entry":
            query = self.get_base_boe_query()
        elif doctype == "Journal Entry":
            query = self.get_base_je_query()
        else:
            frappe.throw(f"Unsupported doctype for GSTR-3B inward data: {doctype}")

        data = query.run(as_dict=True)
        processed_data = self.get_processed_invoices(doctype, data)

        if not group_by_invoice:
            return processed_data

        return self.get_invoice_wise_data(processed_data)

    def get_processed_invoices(self, doctype, data):
        conditions = INWARD_DOCTYPE_CONDITION_MAP[doctype]
        processed_invoices = []
        identified_uom = {}

        for invoice in data:
            if not invoice.invoice_sub_category:
                self.set_invoice_category(invoice, conditions)
                self.set_invoice_sub_category(invoice, conditions)

            invoice.hsn_sub_category = GSTR1_SubCategory.HSN.value

            self.update_tax_values(invoice)

            self.process_uom(invoice, identified_uom)
            processed_invoices.append(invoice)

            if invoice.invoice_category != "ITC Available":
                continue

            if getattr(self, conditions["ITC Reversed"]["category"], None)(invoice):
                reversed_invoice = frappe._dict({**invoice, "invoice_category": "ITC Reversed"})
                self.set_for_itc_reversed(reversed_invoice)
                processed_invoices.append(reversed_invoice)

        return processed_invoices

    def update_tax_values(self, invoice):
        inter = intra = 0
        invoice_type = ""

        if invoice.invoice_category in (
            "Composition Scheme, Exempted, Nil Rated",
            "Non-GST",
        ):
            if is_inter_state_supply(invoice):
                inter = invoice.taxable_value
                invoice_type = "Inter State"
            else:
                intra = invoice.taxable_value
                invoice_type = "Intra State"

        invoice.update(
            {
                "inter": inter,
                "intra": intra,
                "invoice_type": invoice_type,
            }
        )

    def process_uom(self, invoice, identified_uom):
        if invoice.gst_hsn_code and invoice.gst_hsn_code.startswith(SERVICE_HSN_PREFIX):
            invoice["uom"] = "OTH-OTHERS"
            return

        uom = invoice.get("uom", "")
        if uom in identified_uom:
            invoice["uom"] = identified_uom[uom]
        else:
            gst_uom = get_full_gst_uom(uom, self.gst_settings)
            identified_uom[uom] = gst_uom
            invoice["uom"] = gst_uom

    def set_invoice_category(self, invoice, conditions):
        for category, functions in conditions.items():
            if getattr(self, functions["category"])(invoice):
                invoice.invoice_category = category
                return

    def set_invoice_sub_category(self, invoice, conditions):
        category = invoice.invoice_category
        function = conditions[category]["sub_category"]
        getattr(self, function)(invoice)

    def get_invoice_wise_data(self, invoices):
        invoice_wise_data = {}
        for invoice in invoices:
            key = (
                invoice.voucher_type,
                invoice.voucher_no,
                invoice.invoice_category,
                invoice.invoice_sub_category,
            )

            if key not in invoice_wise_data:
                invoice_wise_data[key] = invoice
            else:
                for field in AMOUNT_FIELDS:
                    invoice_wise_data[key][field] += invoice[field]

        return list(invoice_wise_data.values())

    def get_filtered_invoices(self, invoices, subcategories):
        if not subcategories:
            return invoices

        return [invoice for invoice in invoices if invoice.invoice_sub_category in subcategories]
