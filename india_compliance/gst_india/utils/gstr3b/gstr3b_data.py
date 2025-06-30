import frappe
from frappe.query_builder import Case
from frappe.query_builder.custom import ConstantColumn
from frappe.query_builder.functions import IfNull, Sum

from india_compliance.gst_india.constants import GST_TAX_TYPES
from india_compliance.gst_india.overrides.transaction import is_inter_state_supply
from india_compliance.gst_india.utils import get_full_gst_uom
from india_compliance.gst_india.utils.gstr_1 import GSTR1_SubCategory

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

DOCTYPE_CONDITION_MAP = {
    "Purchase Invoice": PURCHASE_CATEGORY_CONDITIONS,
    "Bill of Entry": BOE_CATEGORY_CONDITIONS,
    "Journal Entry": JE_CATEGORY_CONDITIONS,
}

AMOUNT_FIELDS = (
    "igst_amount",
    "cgst_amount",
    "sgst_amount",
    "cess_amount",
    "total_tax",
    "total_amount",
)


class GSTR3BCategoryConditions:
    def is_composition_nil_rated_or_exempted(self, invoice):
        return invoice.gst_category != "Overseas" and (
            invoice.gst_treatment == "Nil-Rated"
            or invoice.gst_treatment == "Exempted"
            or invoice.gst_category == "Registered Composition"
        )

    def is_non_gst(self, invoice):
        return invoice.gst_category != "Overseas" and invoice.gst_treatment == "Non-GST"

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
            "As per rules 42 & 43 of CGST Rules and section 17(5)"
        )

    def set_for_ineligible_itc(self, invoice):
        invoice.invoice_sub_category = "ITC restricted due to PoS rules"

    def set_for_itc_available_boe(self, invoice):
        invoice.invoice_sub_category = "Import Of Goods"

    def set_for_itc_reclaimed(self, invoice):
        invoice.invoice_sub_category = "Reclaim of ITC Reversal"


class GSTR3BQuery:
    def __init__(self, filters):
        self.PI = frappe.qb.DocType("Purchase Invoice")
        self.PI_ITEM = frappe.qb.DocType("Purchase Invoice Item")
        self.BOE = frappe.qb.DocType("Bill of Entry")
        self.BOE_ITEM = frappe.qb.DocType("Bill of Entry Item")
        self.JE = frappe.qb.DocType("Journal Entry")
        self.JE_ACCOUNT = frappe.qb.DocType("Journal Entry Account")
        self.filters = frappe._dict(filters or {})

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
                self.PI_ITEM.item_code,
                IfNull(self.PI_ITEM.gst_treatment, "").as_("gst_treatment"),
                self.PI_ITEM.gst_hsn_code,
                self.PI_ITEM.uom,
                self.PI_ITEM.qty,
                (
                    self.PI_ITEM.cgst_rate
                    + self.PI_ITEM.sgst_rate
                    + self.PI_ITEM.igst_rate
                ).as_("gst_rate"),
                self.PI_ITEM.taxable_value,
                self.PI_ITEM.cgst_amount,
                self.PI_ITEM.sgst_amount,
                self.PI_ITEM.igst_amount,
                (self.PI_ITEM.cess_amount + self.PI_ITEM.cess_non_advol_amount).as_(
                    "cess_amount"
                ),
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
            .where((self.PI.is_opening == "No"))
            .where(self.PI.company_gstin != IfNull(self.PI.supplier_gstin, ""))
            .where(IfNull(self.PI.itc_classification, "") != "Import Of Goods")
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
                self.BOE_ITEM.is_ineligible_for_itc,
                self.BOE_ITEM.item_code,
                self.BOE_ITEM.gst_hsn_code,
                self.BOE_ITEM.uom,
                self.BOE_ITEM.qty,
                (
                    self.BOE_ITEM.cgst_rate
                    + self.BOE_ITEM.sgst_rate
                    + self.BOE_ITEM.igst_rate
                ).as_("gst_rate"),
                self.BOE_ITEM.taxable_value,
                self.BOE_ITEM.cgst_amount,
                self.BOE_ITEM.sgst_amount,
                self.BOE_ITEM.igst_amount,
                (self.BOE_ITEM.cess_amount + self.BOE_ITEM.cess_non_advol_amount).as_(
                    "cess_amount"
                ),
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
                *[
                    Sum(
                        Case()
                        .when(
                            self.JE_ACCOUNT.gst_tax_type.isin(fields),
                            Case()
                            .when(
                                self.JE.voucher_type == "Reversal of ITC",
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
            .where(
                self.JE.voucher_type.isin(
                    ["Reclaim of ITC Reversal", "Reversal of ITC"]
                )
            )
            .groupby(self.JE.name)
        )

        return self.get_query_with_common_filters(query, self.JE)

    def get_query_with_common_filters(self, query, doc):
        query = query.where(
            (doc.docstatus == 1)
            & (doc.posting_date[self.filters.from_date : self.filters.to_date])
            & (doc.company == self.filters.company)
        )

        if self.filters.company_gstin:
            query = query.where(doc.company_gstin == self.filters.company_gstin)

        return query


class GSTR3BInvoices(GSTR3BQuery, GSTR3BSubcategory):
    def get_data(self, doctype, group_by_invoice=False):
        if doctype == "Purchase Invoice":
            query = self.get_base_purchase_query()
        elif doctype == "Bill of Entry":
            query = self.get_base_boe_query()
        elif doctype == "Journal Entry":
            query = self.get_base_je_query()

        data = query.run(as_dict=True)
        processed_data = self.get_processed_invoices(doctype, data)

        if not group_by_invoice:
            return processed_data

        return self.get_invoice_wise_data(processed_data)

    def get_processed_invoices(self, doctype, data):
        conditions = DOCTYPE_CONDITION_MAP[doctype]
        self.gst_settings = frappe.get_cached_doc("GST Settings")
        processed_invoices = []
        identified_uom = {}

        for invoice in data:
            if not invoice.invoice_sub_category:
                self.set_invoice_category(invoice, conditions)
                self.set_invoice_sub_category(invoice, conditions)

            invoice.hsn_sub_category = GSTR1_SubCategory.HSN.value

            if invoice.invoice_category in (
                "Composition Scheme, Exempted, Nil Rated",
                "Non-GST",
            ):
                self.update_tax_values(invoice)

            self.process_uom(invoice, identified_uom)
            processed_invoices.append(invoice)

            if invoice.invoice_category != "ITC Available":
                continue

            if getattr(self, conditions["ITC Reversed"]["category"], None)(invoice):
                reversed_invoice = frappe._dict(
                    {
                        **invoice,
                        "invoice_category": "ITC Reversed",
                        "invoice_sub_category": "As per rules 42 & 43 of CGST Rules and section 17(5)",
                    }
                )
                processed_invoices.append(reversed_invoice)

        return processed_invoices

    def update_tax_values(self, invoice):
        inter = intra = 0

        if is_inter_state_supply(invoice):
            inter = invoice.taxable_value
        else:
            intra = invoice.taxable_value

        invoice.update(
            {
                "inter": inter,
                "intra": intra,
                "invoice_type": "Inter State" if inter else "Intra State",
            }
        )

    def process_uom(self, invoice, identified_uom):
        if invoice.gst_hsn_code and invoice.gst_hsn_code.startswith("99"):
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
            if getattr(self, functions["category"], None)(invoice):
                invoice.invoice_category = category
                return

    def set_invoice_sub_category(self, invoice, conditions):
        category = invoice.invoice_category
        function = conditions[category]["sub_category"]
        getattr(self, function, None)(invoice)

    def get_invoice_wise_data(self, invoices):
        invoice_wise_data = {}
        for invoice in invoices:
            key = f"{invoice.voucher_no}-{invoice.invoice_category}-{invoice.invoice_sub_category}"

            if key not in invoice_wise_data:
                invoice_wise_data[key] = invoice
            else:
                for field in AMOUNT_FIELDS:
                    invoice_wise_data[key][field] += invoice[field]

        return list(invoice_wise_data.values())

    def get_filtered_invoices(self, invoices, subcategories):
        if not subcategories:
            return invoices

        return [
            invoice
            for invoice in invoices
            if invoice.invoice_sub_category in subcategories
        ]
