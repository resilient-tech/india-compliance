# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt

import frappe

from india_compliance.gst_india.utils import get_gst_accounts_by_type
from india_compliance.gst_india.utils.gstr3b.gstr3b_inward_data import GSTR3BQuery
from india_compliance.gst_india.utils.gstr_1.gstr_1_data import GSTR1Query, GSTR11A11BData

# GST categories that need to be reported in section 3.2 (inter-state supplies)
INTER_STATE_GST_CATEGORIES = frozenset({"Unregistered", "Registered Composition", "UIN Holders"})

# Maps JSON tax keys to SI item field names
GSTR1_FIELD_MAP = {
    "iamt": "igst_amount",
    "camt": "cgst_amount",
    "samt": "sgst_amount",
    "csamt": "total_cess_amount",
}

# JSON tax keys to accumulate per 3B section (sections absent here get txval only)
OUTWARD_SECTION_TAX_FIELDS = {
    "osup_zero": ("iamt", "csamt"),
    "osup_det": ("iamt", "camt", "samt", "csamt"),
    "isup_rev": ("iamt", "camt", "samt", "csamt"),
}

# Maps GST category → inter-state supply sub-section in the JSON
INTER_STATE_SECTION_MAP = {
    "Unregistered": "unreg_details",
    "Registered Composition": "comp_details",
    "UIN Holders": "uin_details",
}

OUTWARD_CATEGORY_LABELS = {
    "outward_taxable": "Outward taxable supplies (other than zero rated, nil rated and exempted)",
    "outward_zero_rated": "Outward taxable supplies (zero rated)",
    "other_outward": "Other outward supplies (Nil rated, exempted)",
    "outward_non_gst": "Non-GST outward supplies",
    "inward_reverse_charge": "Inward supplies (liable to reverse charge)",
    "eco_9_5": (
        "Supplies made through e-commerce operators on which e-commerce operator is liable "
        "to pay tax u/s 9(5)"
    ),
}

OUTWARD_SUB_CATEGORY_LABELS = {
    "nil_exempt": "Nil-Rated, Exempted",
    "non_gst": "Non-GST",
    "ecom_9_5": "E-Commerce 9(5)",
    "zero_rated": "Zero-Rated",
    "taxable": "Taxable",
    "regular": "Regular",
    "inward_reverse_charge": "Inward Reverse Charge",
}

OUTWARD_INTER_STATE_FIELD = "is_part_of_inter_state_supplies"

OUTWARD_SECTION_LABELS = {
    "sup_details": "Details of Outward Supplies and inward supplies liable to reverse charge",
    "eco_dtls": "Supplies notified under section 9(5) of the CGST Act, 2017",
}

OUTWARD_SECTION_MAP = {
    "sup_details": {
        "osup_det": OUTWARD_CATEGORY_LABELS["outward_taxable"],
        "osup_zero": OUTWARD_CATEGORY_LABELS["outward_zero_rated"],
        "osup_nil_exmp": OUTWARD_CATEGORY_LABELS["other_outward"],
        "isup_rev": OUTWARD_CATEGORY_LABELS["inward_reverse_charge"],
        "osup_nongst": OUTWARD_CATEGORY_LABELS["outward_non_gst"],
    },
    "eco_dtls": {
        "eco_reg_sup": OUTWARD_CATEGORY_LABELS["eco_9_5"],
    },
}

OUTWARD_SALES_CATEGORY_CONDITIONS = {
    "nil_exempt": {
        "section": "sup_details",
        "row": "osup_nil_exmp",
        "category": "is_nil_rated_exempted",
        "sub_category": "set_for_nil_rated_exempted",
    },
    "non_gst": {
        "section": "sup_details",
        "row": "osup_nongst",
        "category": "is_non_gst",
        "sub_category": "set_for_non_gst",
    },
    "ecom_9_5": {
        "section": "eco_dtls",
        "row": "eco_reg_sup",
        "category": "is_ecom_9_5",
        "sub_category": "set_for_ecom_9_5",
    },
    "zero_rated": {
        "section": "sup_details",
        "row": "osup_zero",
        "category": "is_zero_rated",
        "sub_category": "set_for_zero_rated",
    },
    "taxable": {
        "section": "sup_details",
        "row": "osup_det",
        "category": "is_taxable",
        "sub_category": "set_for_taxable",
    },
}

OUTWARD_PURCHASE_CATEGORY_CONDITIONS = {
    "inward_rc": {
        "section": "sup_details",
        "row": "isup_rev",
        "category": "is_inward_reverse_charge",
        "sub_category": "set_for_inward_reverse_charge",
    }
}

DOCTYPE_CONDITION_MAP = {
    "Sales Invoice": OUTWARD_SALES_CATEGORY_CONDITIONS,
    "Purchase Invoice": OUTWARD_PURCHASE_CATEGORY_CONDITIONS,
}


class GSTR3BOutwardConditions:
    def is_nil_rated_exempted(self, invoice):
        return invoice.gst_treatment in ("Nil-Rated", "Exempted")

    def is_non_gst(self, invoice):
        return invoice.gst_treatment == "Non-GST"

    def is_ecom_9_5(self, invoice):
        # Supply liable to pay tax u/s 9(5): ecommerce operator pays, marked RC on SI
        return bool(invoice.ecommerce_gstin) and bool(invoice.is_reverse_charge)

    def is_zero_rated(self, invoice):
        return invoice.gst_treatment == "Zero-Rated"

    def is_taxable(self, invoice):
        return not (
            self.is_nil_rated_exempted(invoice)
            or self.is_non_gst(invoice)
            or self.is_ecom_9_5(invoice)
            or self.is_zero_rated(invoice)
        )

    def is_inward_reverse_charge(self, invoice):
        return bool(invoice.is_reverse_charge)


class GSTR3BOutwardSubcategory(GSTR3BOutwardConditions):
    def set_for_nil_rated_exempted(self, invoice):
        invoice.invoice_sub_category = OUTWARD_SUB_CATEGORY_LABELS["nil_exempt"]

    def set_for_non_gst(self, invoice):
        invoice.invoice_sub_category = OUTWARD_SUB_CATEGORY_LABELS["non_gst"]

    def set_for_ecom_9_5(self, invoice):
        invoice.invoice_sub_category = OUTWARD_SUB_CATEGORY_LABELS["ecom_9_5"]

    def set_for_zero_rated(self, invoice):
        invoice.invoice_sub_category = OUTWARD_SUB_CATEGORY_LABELS["zero_rated"]

    def set_for_taxable(self, invoice):
        invoice.invoice_sub_category = OUTWARD_SUB_CATEGORY_LABELS["taxable"]

    def set_for_inward_reverse_charge(self, invoice):
        invoice.invoice_sub_category = OUTWARD_SUB_CATEGORY_LABELS["inward_reverse_charge"]


class GSTR3BOutwardInvoices(GSTR3BOutwardSubcategory):
    def __init__(self, filters):
        self.filters = filters
        self.gstr3b_query = GSTR3BQuery(filters)
        self.gstr1_query = GSTR1Query(filters)

    def get_data(self):
        return (
            self.get_outward_invoices() + self.get_inward_invoices() + self.get_advance_adjustment_invoices()
        )

    def get_outward_invoices(self):
        data = self.gstr1_query.get_base_query().run(as_dict=True)
        return self.get_processed_invoices("Sales Invoice", data)

    def get_inward_invoices(self):
        purchase_data = (
            self.gstr3b_query.get_base_purchase_query()
            .where(self.gstr3b_query.PI.is_reverse_charge == 1)
            .run(as_dict=True)
        )

        return self.get_processed_invoices("Purchase Invoice", purchase_data)

    def get_advance_adjustment_invoices(self):
        gst_accounts = get_gst_accounts_by_type(self.filters.company, "Output")
        advance_data = GSTR11A11BData(self.filters, gst_accounts)
        invoices = []

        for method, fields, multiplier in (
            (
                "get_11A_query",
                (
                    advance_data.pe.name.as_("invoice_no"),
                    advance_data.pe.party.as_("customer_name"),
                    advance_data.pe.posting_date,
                    advance_data.pe.company_gstin,
                ),
                1,
            ),
            (
                "get_11B_query",
                (
                    advance_data.pe.name.as_("invoice_no"),
                    advance_data.pe.party.as_("customer_name"),
                    advance_data.pe.posting_date,
                    advance_data.pe.company_gstin,
                    advance_data.pe_ref.reference_name.as_("return_against"),
                ),
                -1,
            ),
        ):
            query = getattr(advance_data, method)().select(*fields)
            data = query.run(as_dict=True)
            invoices.extend(self.get_advance_adjustment_rows(data, multiplier))

        return invoices

    def get_advance_adjustment_rows(self, data, multiplier):
        rows = []
        for row in data:
            is_intra_state = row["place_of_supply"][:2] == row["company_gstin"][:2]
            tax_amount = row["tax_amount"] * multiplier
            tax_rate = round((row["tax_amount"] / row["taxable_value"]) * 100) if row["taxable_value"] else 0

            invoice = frappe._dict(
                {
                    "invoice_category": "sup_details",
                    "invoice_category_label": OUTWARD_SECTION_LABELS["sup_details"],
                    "outward_section": "osup_det",
                    "outward_section_label": OUTWARD_SECTION_MAP["sup_details"]["osup_det"],
                    "invoice_no": row.invoice_no,
                    "customer_name": row.customer_name,
                    "voucher_type": "Payment Entry",
                    "posting_date": row.posting_date,
                    "company_gstin": row.company_gstin,
                    "invoice_sub_category": OUTWARD_SUB_CATEGORY_LABELS["regular"],
                    "taxable_value": row.taxable_value * multiplier,
                    "gst_rate": tax_rate,
                    "igst_amount": 0 if is_intra_state else tax_amount,
                    "cgst_amount": (tax_amount / 2) if is_intra_state else 0,
                    "sgst_amount": (tax_amount / 2) if is_intra_state else 0,
                    "total_cess_amount": row.cess_amount * multiplier,
                    "gst_category": "",
                    "place_of_supply": row.place_of_supply,
                    OUTWARD_INTER_STATE_FIELD: 0,
                    "doctype": "Payment Entry",
                }
            )

            if row.get("return_against"):
                invoice.return_against = row.return_against

            rows.append(invoice)

        return rows

    def get_processed_invoices(self, doctype, data):
        conditions = DOCTYPE_CONDITION_MAP[doctype]
        processed = []
        for invoice in data:
            invoice[OUTWARD_INTER_STATE_FIELD] = 0

            if doctype != "Sales Invoice":
                invoice.total_cess_amount = invoice.get("cess_amount") or 0

            self.set_invoice_category(invoice, conditions)
            if not invoice.get("invoice_category"):
                continue

            self.set_invoice_sub_category(invoice, conditions)
            self.set_tax_amounts(invoice, doctype)
            self.set_3_1_a(invoice, doctype)
            processed.append(invoice)

        return processed

    def set_3_1_a(self, invoice, doctype):
        invoice[OUTWARD_INTER_STATE_FIELD] = int(self.is_part_of_inter_state_supplies(invoice, doctype))

    def set_tax_amounts(self, invoice, doctype):
        # From RCM Sales Invoices, no tax is charged.
        if doctype != "Sales Invoice" or not invoice.get("is_reverse_charge"):
            return

        invoice.igst_amount = 0
        invoice.cgst_amount = 0
        invoice.sgst_amount = 0
        invoice.total_cess_amount = 0

    def is_part_of_inter_state_supplies(self, invoice, doctype):
        return (
            doctype == "Sales Invoice"
            and invoice.get("outward_section") == "osup_det"
            and invoice.get("gst_category") in INTER_STATE_GST_CATEGORIES
            and (invoice.get("igst_amount") or 0) > 0
            and (invoice.get("gst_rate") or 0) > 0
        )

    def set_invoice_category(self, invoice, conditions):
        for condition_key, functions in conditions.items():
            if getattr(self, functions["category"])(invoice):
                invoice.invoice_category = functions["section"]
                invoice.invoice_category_label = OUTWARD_SECTION_LABELS[functions["section"]]
                invoice.outward_section = functions["row"]
                invoice.outward_section_label = OUTWARD_SECTION_MAP[functions["section"]][functions["row"]]
                invoice.outward_condition_key = condition_key
                return

    def set_invoice_sub_category(self, invoice, conditions):
        function = conditions[invoice.outward_condition_key]["sub_category"]
        getattr(self, function)(invoice)
