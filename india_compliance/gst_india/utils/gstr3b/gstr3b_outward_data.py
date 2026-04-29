# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt

import frappe

from india_compliance.gst_india.utils import get_gst_accounts_by_type
from india_compliance.gst_india.utils.gstr3b.gstr3b_inward_data import GSTR3BInwardQuery
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

OUTWARD_INTER_STATE_FIELD = "is_part_of_inter_state_supplies"

OUTWARD_CATEGORY_MAP = {
    "Details of Outward Supplies and inward supplies liable to reverse charge": "sup_details",
    "Supplies notified under section 9(5) of the CGST Act, 2017": "eco_dtls",
}

OUTWARD_SUB_CATEGORY_MAP = {
    "Nil-Rated, Exempted": "osup_nil_exmp",
    "Non-GST": "osup_nongst",
    "E-Commerce 9(5)": "eco_reg_sup",
    "Zero-Rated": "osup_zero",
    "Taxable": "osup_det",
    "Inward Reverse Charge": "isup_rev",
}

OUTWARD_AMOUNT_FIELDS = (
    "taxable_value",
    "igst_amount",
    "cgst_amount",
    "sgst_amount",
    "total_cess_amount",
)

OUTWARD_SALES_CATEGORY_CONDITIONS = {
    "Nil-Rated, Exempted": {
        "condition": "is_nil_rated_exempted",
        "invoice_category": "Details of Outward Supplies and inward supplies liable to reverse charge",
    },
    "Non-GST": {
        "condition": "is_non_gst",
        "invoice_category": "Details of Outward Supplies and inward supplies liable to reverse charge",
    },
    "E-Commerce 9(5)": {
        "condition": "is_ecom_9_5",
        "invoice_category": "Supplies notified under section 9(5) of the CGST Act, 2017",
    },
    "Zero-Rated": {
        "condition": "is_zero_rated",
        "invoice_category": "Details of Outward Supplies and inward supplies liable to reverse charge",
    },
    "Taxable": {
        "condition": "is_taxable",
        "invoice_category": "Details of Outward Supplies and inward supplies liable to reverse charge",
    },
}

OUTWARD_PURCHASE_CATEGORY_CONDITIONS = {
    "Inward Reverse Charge": {
        "condition": "is_inward_reverse_charge",
        "invoice_category": "Details of Outward Supplies and inward supplies liable to reverse charge",
    }
}

OUTWARD_DOCTYPE_CONDITION_MAP = {
    "Sales Invoice": OUTWARD_SALES_CATEGORY_CONDITIONS,
    "Purchase Invoice": OUTWARD_PURCHASE_CATEGORY_CONDITIONS,
}


class GSTR3BCategoryConditions:
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


class GSTR3BOutwardInvoices(GSTR3BCategoryConditions):
    def __init__(self, filters):
        self.filters = filters
        self.inward_query = GSTR3BInwardQuery(filters)
        self.gstr1_query = GSTR1Query(filters)

    def get_data(self, group_by_invoice=False):
        data = (
            self.get_outward_invoices() + self.get_inward_invoices() + self.get_advance_adjustment_invoices()
        )

        if not group_by_invoice:
            return data

        return self.get_invoice_wise_data(data)

    def get_outward_invoices(self):
        data = self.gstr1_query.get_base_query().run(as_dict=True)
        return self.get_processed_invoices("Sales Invoice", data)

    def get_inward_invoices(self):
        purchase_data = (
            self.inward_query.get_base_purchase_query()
            .select(
                self.inward_query.PI.name.as_("invoice_no"),
                (self.inward_query.PI_ITEM.cess_amount + self.inward_query.PI_ITEM.cess_non_advol_amount).as_(
                    "total_cess_amount"
                )
            )
            .where(self.inward_query.PI.is_reverse_charge == 1)
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
            is_intra_state = (row.get("place_of_supply") or "")[:2] == (row.get("company_gstin") or "")[:2]
            tax_amount = row["tax_amount"] * multiplier
            tax_rate = (
                round((row["tax_amount"] / row["taxable_value"]) * 100, 2) if row["taxable_value"] else 0
            )

            invoice = frappe._dict(
                {
                    "invoice_category": "Details of Outward Supplies and inward supplies liable to reverse charge",
                    "invoice_sub_category": "Taxable",
                    "invoice_no": row.invoice_no,
                    "customer_name": row.customer_name,
                    "voucher_type": "Payment Entry",
                    "posting_date": row.posting_date,
                    "company_gstin": row.company_gstin,
                    "taxable_value": row.taxable_value * multiplier,
                    "gst_rate": tax_rate,
                    "igst_amount": 0 if is_intra_state else tax_amount,
                    "cgst_amount": round(tax_amount / 2, 2) if is_intra_state else 0,
                    "sgst_amount": round(tax_amount / 2, 2) if is_intra_state else 0,
                    "total_cess_amount": row.cess_amount * multiplier,
                    "gst_category": "",
                    "place_of_supply": row.place_of_supply,
                    OUTWARD_INTER_STATE_FIELD: 0,
                }
            )

            if row.get("return_against"):
                invoice.return_against = row.return_against

            rows.append(invoice)

        return rows

    def get_processed_invoices(self, doctype, data):
        conditions = OUTWARD_DOCTYPE_CONDITION_MAP[doctype]
        processed = []
        for invoice in data:
            invoice[OUTWARD_INTER_STATE_FIELD] = 0

            self.set_invoice_category(invoice, conditions)
            if not invoice.get("invoice_sub_category"):
                continue

            self.set_tax_amounts(invoice, doctype)
            self.set_inter_state_supply_flag(invoice, doctype)
            processed.append(invoice)

        return processed

    def set_inter_state_supply_flag(self, invoice, doctype):
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
            and invoice.invoice_sub_category == "Taxable"
            and invoice.gst_category in INTER_STATE_GST_CATEGORIES
            and (invoice.igst_amount or 0) > 0
            and (invoice.gst_rate or 0) > 0
        )

    def set_invoice_category(self, invoice, conditions):
        for sub_category, functions in conditions.items():
            if getattr(self, functions["condition"])(invoice):
                invoice.invoice_category = functions["invoice_category"]
                invoice.invoice_sub_category = sub_category
                return

    def update_invoice_amounts(self, target_invoice, source_invoice):
        for field in OUTWARD_AMOUNT_FIELDS:
            target_invoice[field] += source_invoice[field]

    def get_invoice_wise_data(self, invoices):
        invoice_wise_data = {}
        for invoice in invoices:
            key = (
                invoice.voucher_type,
                invoice.invoice_no,
                invoice.invoice_category,
                invoice.invoice_sub_category,
            )

            aggregated_invoice = invoice_wise_data.get(key)
            if not aggregated_invoice:
                invoice_wise_data[key] = invoice
                continue

            self.update_invoice_amounts(aggregated_invoice, invoice)

        return list(invoice_wise_data.values())
