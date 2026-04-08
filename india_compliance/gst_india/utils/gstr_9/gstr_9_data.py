# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe.query_builder import Case, Criterion
from frappe.query_builder.functions import IfNull, Max, Sum
from frappe.utils import flt

from india_compliance.gst_india.utils.gstr_1.gstr_1_data import (
    GSTR1Query,
    cache_invoice_condition,
)
from india_compliance.gst_india.utils.gstr_9 import (
    GSTR9_Row,
    _empty_row,
)


class GSTR9BooksData(GSTR1Query):
    """
    Computes GSTR-9 books data from ERP (Sales/Purchase Invoices, Journal Entries) for a given company, GSTIN, and financial year.

    Inherits GSTR1Query to reuse self.si, self.si_item DocType references and get_query_with_common_filters() for applying company/GSTIN/date filters without duplication.

    Uses frappe.db.unbuffered_cursor() (SSCursor) so rows are streamed from the server one at a time — classification happens in a Python loop without loading the full result set into memory.

    Returns classified invoice-level data (books format):
      {row_key: {doc_number: invoice_dict}}  — for drillable rows (GSTR-1 style)
      {row_key: {amount_fields}}             — for manual/aggregated-only rows
      {row_key: special_structure}           — for Tables 14, 15, 17, 18
    """

    def __init__(self, filters):
        # Sets self.si, self.si_item, self.si_taxes, self.filters
        super().__init__(filters)
        self.company = self.filters.company
        self.company_gstin = self.filters.company_gstin
        self.from_date = self.filters.from_date
        self.to_date = self.filters.to_date

    def get_data(self):
        """
        Returns books data.

        Invoice dicts are stored for drillable rows (GSTR-1 nested-dict
        format) so the detail view can read from the cached snapshot
        without re-querying.
        """
        data = {}

        # Fetch all outward (Sales Invoice) items once, classify into Table 4 & 5
        data.update(self._get_classified_outward_supplies())

        # Fetch all purchase items once, classify into Table 4G & Table 6
        data.update(self._get_classified_purchase_invoices())

        # BOE records → split into 6E Inputs / 6E Capital Goods
        for row_key, records in self._get_boe_books().items():
            if records:
                data.setdefault(row_key, {}).update(records)

        # Advances (4F) — reuses GSTR-1 advance query logic
        data[GSTR9_Row.TABLE_4F] = self._get_advances_data()

        # Manual / empty rows
        for key in (
            GSTR9_Row.TABLE_4G1,
            GSTR9_Row.TABLE_4K,
            GSTR9_Row.TABLE_4L,
            GSTR9_Row.TABLE_5J,
            GSTR9_Row.TABLE_5K,
        ):
            data[key] = _empty_row()

        for key in (
            GSTR9_Row.TABLE_6A,
            GSTR9_Row.TABLE_6A1,
            GSTR9_Row.TABLE_6H,
            GSTR9_Row.TABLE_6K,
            GSTR9_Row.TABLE_6L,
            GSTR9_Row.TABLE_6M,
        ):
            data[key] = _empty_row()

        # Ensure all drillable row keys exist (empty list if no data)
        for key in (
            # Table 4 outward
            GSTR9_Row.TABLE_4A,
            GSTR9_Row.TABLE_4B,
            GSTR9_Row.TABLE_4C,
            GSTR9_Row.TABLE_4D,
            GSTR9_Row.TABLE_4E,
            GSTR9_Row.TABLE_4G,
            GSTR9_Row.TABLE_4I,
            GSTR9_Row.TABLE_4J,
            # Table 5 outward
            GSTR9_Row.TABLE_5A,
            GSTR9_Row.TABLE_5B,
            GSTR9_Row.TABLE_5C,
            GSTR9_Row.TABLE_5C1,
            GSTR9_Row.TABLE_5D,
            GSTR9_Row.TABLE_5E,
            GSTR9_Row.TABLE_5F,
            GSTR9_Row.TABLE_5H,
            GSTR9_Row.TABLE_5I,
            # Table 6 ITC
            GSTR9_Row.TABLE_6B_INPUTS,
            GSTR9_Row.TABLE_6B_CAPITAL_GOODS,
            GSTR9_Row.TABLE_6B_INPUT_SERVICES,
            GSTR9_Row.TABLE_6C_INPUTS,
            GSTR9_Row.TABLE_6C_CAPITAL_GOODS,
            GSTR9_Row.TABLE_6C_INPUT_SERVICES,
            GSTR9_Row.TABLE_6D_INPUTS,
            GSTR9_Row.TABLE_6D_CAPITAL_GOODS,
            GSTR9_Row.TABLE_6D_INPUT_SERVICES,
            GSTR9_Row.TABLE_6E_INPUTS,
            GSTR9_Row.TABLE_6E_CAPITAL_GOODS,
            GSTR9_Row.TABLE_6F,
            GSTR9_Row.TABLE_6G,
        ):
            data.setdefault(key, [])

        data.update(self._get_table_7_data())
        data.update(self._get_table_10_to_13_data())
        data.update(self._get_table_14_data())
        data.update(self._get_table_15_data())
        data.update(self._get_table_16_data())
        data.update(self._get_table_17_data())
        data.update(self._get_table_18_data())

        return data

    def _get_table_7_data(self):
        data = {}
        data[GSTR9_Row.TABLE_7A] = _empty_row()
        data[GSTR9_Row.TABLE_7A1] = _empty_row()
        data[GSTR9_Row.TABLE_7A2] = _empty_row()
        data[GSTR9_Row.TABLE_7B] = _empty_row()
        data[GSTR9_Row.TABLE_7C] = _empty_row()
        data[GSTR9_Row.TABLE_7D] = _empty_row()
        data[GSTR9_Row.TABLE_7E] = _empty_row()
        data[GSTR9_Row.TABLE_7F] = _empty_row()
        data[GSTR9_Row.TABLE_7G] = _empty_row()
        data[GSTR9_Row.TABLE_7H1] = _empty_row()

        return data

    def _get_table_10_to_13_data(self):
        return {
            GSTR9_Row.TABLE_10: _empty_row(),
            GSTR9_Row.TABLE_11: _empty_row(),
            GSTR9_Row.TABLE_12: _empty_row(),
            GSTR9_Row.TABLE_13: _empty_row(),
        }

    def _get_table_14_data(self):
        return {
            GSTR9_Row.TABLE_14: [
                {
                    "label": "A",
                    "description": "Integrated Tax",
                    "payable": 0,
                    "paid": 0,
                },
                {"label": "B", "description": "Central Tax", "payable": 0, "paid": 0},
                {"label": "C", "description": "State/UT Tax", "payable": 0, "paid": 0},
                {"label": "D", "description": "Cess", "payable": 0, "paid": 0},
                {"label": "E", "description": "Interest", "payable": None, "paid": 0},
            ]
        }

    def _get_table_15_data(self):

        def _row(label, description):
            return {
                "label": label,
                "description": description,
                "igst": 0,
                "cgst": 0,
                "sgst": 0,
                "cess": 0,
                "interest": 0,
                "penalty": 0,
                "late_fee": 0,
            }

        return {
            GSTR9_Row.TABLE_15: [
                _row("A", "Total Refund claimed"),
                _row("B", "Total Refund sanctioned"),
                _row("C", "Total Refund Rejected"),
                _row("D", "Total Refund Pending"),
                _row("E", "Total demand of taxes adjudicated"),
                _row("F", "Total taxes paid in respect of E above"),
                _row("G", "Total demands pending out of E above"),
            ]
        }

    def _get_table_16_data(self):
        return {
            GSTR9_Row.TABLE_16A: _empty_row(),
            GSTR9_Row.TABLE_16B: _empty_row(),
            GSTR9_Row.TABLE_16C: _empty_row(),
        }

    def _get_table_17_data(self):
        return {GSTR9_Row.TABLE_17: self._get_hsn_data("outward")}

    def _get_table_18_data(self):
        return {GSTR9_Row.TABLE_18: self._get_hsn_data("inward")}

    def _get_hsn_data(self, direction):
        """Reuse the standalone HSN report functions for exact data parity.

        Converts report field names to the GSTR-9 display format and splits
        into goods (HSN not starting with '99') and services (SAC codes).
        """
        from india_compliance.gst_india.report.hsn_wise_summary_of_inward_supplies.hsn_wise_summary_of_inward_supplies import (
            get_data as get_inward_hsn_data,
        )
        from india_compliance.gst_india.report.hsn_wise_summary_of_outward_supplies.hsn_wise_summary_of_outward_supplies import (
            get_hsn_data as get_outward_hsn_data,
        )

        filters = frappe._dict(
            company=self.company,
            company_gstin=self.company_gstin,
            from_date=self.from_date,
            to_date=self.to_date,
            filter_by="Posting Date",  # GSTR-9 always uses posting date range
        )

        rows = (
            get_outward_hsn_data(filters)
            if direction == "outward"
            else get_inward_hsn_data(filters)
        )

        goods, services = [], []
        for row in rows:
            mapped = {
                "hsn_code": row.get("hsn_code"),
                "description": row.get("description"),
                "uom": row.get("uom"),
                "tax_rate": row.get("tax_rate"),
                "quantity": row.get("quantity"),
                "taxable_value": row.get("total_taxable_value"),
                "igst": row.get("total_igst_amount"),
                "cgst": row.get("total_cgst_amount"),
                "sgst": row.get("total_sgst_amount"),
                "cess": row.get("total_cess_amount"),
            }
            (
                services if str(row.get("hsn_code") or "").startswith("99") else goods
            ).append(mapped)

        return {"goods": goods, "services": services}

    # ────────────────────────────────────────────────────────
    # Outward Supplies — Tables 4 & 5
    # ────────────────────────────────────────────────────────

    def _get_classified_outward_supplies(self):
        """
        Fetch all Sales Invoice items in a single query, classify each item
        into a GSTR-9 row in Python, and accumulate per (row_key, invoice).

        Uses unbuffered cursor (SSCursor) so rows are streamed from the server
        one at a time instead of loading the full result set into memory.

        Returns {row_key: [invoice_dicts]}.
        """
        query = self._get_outward_items_query()
        classifier = GSTR9OutwardClassifier()
        accumulator = {}

        with frappe.db.unbuffered_cursor():
            for item in frappe.db.sql(query.get_sql(), as_dict=True, as_iterator=True):
                row_key = classifier.classify(item)
                if not row_key:
                    continue

                _accumulate_item(
                    accumulator,
                    row_key,
                    item.name,
                    item,
                    party_name_field="customer_name",
                    party_gstin_field="billing_address_gstin",
                    party_gstin_key="customer_gstin",
                    is_purchase=False,
                )

        return _build_result(accumulator)

    def _get_outward_items_query(self):
        """
        Build the outward supply query using GSTR-1's common filter infrastructure.

        Calls get_query_with_common_filters() (inherited from GSTR1Query) to
        apply company / company_gstin / from_date / to_date filters — reusing
        the GSTR-1 filter logic instead of duplicating it.
        """
        query = (
            frappe.qb.from_(self.si)
            .inner_join(self.si_item)
            .on(
                (self.si_item.parent == self.si.name)
                & (self.si_item.parenttype == "Sales Invoice")
            )
            .select(
                self.si.name,
                self.si.posting_date,
                self.si.customer,
                self.si.customer_name,
                self.si.billing_address_gstin,
                self.si.gst_category,
                self.si.place_of_supply,
                self.si.is_return,
                self.si.is_debit_note,
                self.si.is_reverse_charge,
                self.si.is_export_with_gst,
                self.si.base_rounded_total,
                self.si.base_grand_total,
                IfNull(self.si.shipping_bill_number, "").as_("shipping_bill_number"),
                self.si.shipping_bill_date,
                IfNull(self.si.port_code, "").as_("port_code"),
                IfNull(self.si.ecommerce_gstin, "").as_("ecommerce_gstin"),
                IfNull(self.si_item.gst_treatment, "").as_("gst_treatment"),
                self.si_item.taxable_value,
                self.si_item.igst_amount.as_("igst"),
                self.si_item.cgst_amount.as_("cgst"),
                self.si_item.sgst_amount.as_("sgst"),
                self.si_item.cess_amount.as_("cess"),
                (
                    self.si_item.igst_rate
                    + self.si_item.cgst_rate
                    + self.si_item.sgst_rate
                ).as_("tax_rate"),
            )
            .where(self.si.docstatus == 1)
            .where(self.si.is_opening != "Yes")
            .orderby(self.si.posting_date)
        )
        # Applies company / company_gstin / from_date / to_date — reuses GSTR-1 logic
        return self.get_query_with_common_filters(query)

    # ────────────────────────────────────────────────────────
    # Purchase Invoices — Table 4G & Table 6
    # ────────────────────────────────────────────────────────

    def _get_classified_purchase_invoices(self):
        """
        Fetch all relevant Purchase Invoice items in a single query, classify
        each item for Table 4G (RCM) and/or Table 6 (ITC), and accumulate.

        A single invoice item can contribute to BOTH 4G and a Table 6 row.
        Uses unbuffered cursor (SSCursor) so rows are streamed from the server
        one at a time instead of loading the full result set into memory.

        Returns {row_key: [invoice_dicts]}.
        """
        query = self._get_purchase_items_query()
        classifier = GSTR9PurchaseClassifier(self.company_gstin)
        accumulator = {}

        with frappe.db.unbuffered_cursor():
            for item in frappe.db.sql(query.get_sql(), as_dict=True, as_iterator=True):
                rcm_key, itc_key = classifier.classify(item)

                if rcm_key:
                    _accumulate_item(
                        accumulator,
                        rcm_key,
                        item.name,
                        item,
                        party_name_field="supplier_name",
                        party_gstin_field="supplier_gstin",
                        party_gstin_key="supplier_gstin",
                        is_purchase=True,
                    )

                if itc_key:
                    _accumulate_item(
                        accumulator,
                        itc_key,
                        item.name,
                        item,
                        party_name_field="supplier_name",
                        party_gstin_field="supplier_gstin",
                        party_gstin_key="supplier_gstin",
                        is_purchase=True,
                        extra_fields={"itc_classification": item.itc_classification},
                    )

        return _build_result(accumulator)

    def _get_purchase_items_query(self):
        """
        Build the purchase items query (GSTR-1 has no PI equivalent, so filters
        are applied directly here rather than via get_query_with_common_filters).

        Includes items from invoices that are EITHER:
        - Reverse charge (for Table 4G)
        - Have ITC classification (for Table 6)
        """
        pi = frappe.qb.DocType("Purchase Invoice")
        pi_item = frappe.qb.DocType("Purchase Invoice Item")
        item_doc = frappe.qb.DocType("Item")

        rcm_condition = pi.is_reverse_charge == 1
        itc_condition = (IfNull(pi.itc_classification, "") != "") & (
            pi.company_gstin != IfNull(pi.supplier_gstin, "")
        )

        return (
            frappe.qb.from_(pi)
            .inner_join(pi_item)
            .on(
                (pi_item.parent == pi.name) & (pi_item.parenttype == "Purchase Invoice")
            )
            .left_join(item_doc)
            .on(item_doc.name == pi_item.item_code)
            .select(
                pi.name,
                pi.posting_date,
                pi.supplier,
                pi.supplier_name,
                pi.supplier_gstin,
                pi.gst_category,
                pi.place_of_supply,
                pi.is_return,
                pi.is_reverse_charge,
                pi.base_rounded_total,
                pi.base_grand_total,
                IfNull(pi.itc_classification, "").as_("itc_classification"),
                IfNull(pi.ineligibility_reason, "").as_("ineligibility_reason"),
                pi_item.is_fixed_asset,
                IfNull(item_doc.is_stock_item, 1).as_("is_stock_item"),
                pi_item.taxable_value,
                pi_item.igst_amount.as_("igst"),
                pi_item.cgst_amount.as_("cgst"),
                pi_item.sgst_amount.as_("sgst"),
                pi_item.cess_amount.as_("cess"),
                (pi_item.igst_rate + pi_item.cgst_rate + pi_item.sgst_rate).as_(
                    "tax_rate"
                ),
            )
            .where(
                (pi.docstatus == 1)
                & (pi.is_opening != "Yes")
                & (pi.company == self.company)
                & (pi.company_gstin == self.company_gstin)
                & (pi.posting_date.between(self.from_date, self.to_date))
                & Criterion.any([rcm_condition, itc_condition])
            )
            .orderby(pi.posting_date)
        )

    def _get_boe_books(self):
        """
        Individual Bill of Entry records with IGST/Cess amounts and supplier
        info resolved from linked Purchase Invoices.

        A single aggregated query joins boe_taxes, boe_item→pi, and
        boe_item→pi_item so that tax totals, supplier details, and the
        capital-goods flag are all computed in one database round-trip.

        Returns {TABLE_6E_INPUTS: [...], TABLE_6E_CAPITAL_GOODS: [...]}.
        """
        boe = frappe.qb.DocType("Bill of Entry")
        boe_taxes = frappe.qb.DocType("India Compliance Taxes and Charges")
        boe_item = frappe.qb.DocType("Bill of Entry Item")
        pi = frappe.qb.DocType("Purchase Invoice")
        pi_item = frappe.qb.DocType("Purchase Invoice Item")

        rows = (
            frappe.qb.from_(boe)
            .left_join(boe_taxes)
            .on(
                (boe_taxes.parent == boe.name)
                & (boe_taxes.parenttype == "Bill of Entry")
            )
            .left_join(boe_item)
            .on(boe_item.parent == boe.name)
            .left_join(pi)
            .on(
                (pi.name == boe_item.purchase_invoice)
                & (IfNull(boe_item.purchase_invoice, "") != "")
            )
            .left_join(pi_item)
            .on(boe_item.pi_detail == pi_item.name)
            .select(
                boe.name.as_("document_number"),
                boe.posting_date,
                boe.total_taxable_value.as_("taxable_value"),
                Sum(
                    Case()
                    .when(boe_taxes.gst_tax_type == "igst", boe_taxes.tax_amount)
                    .else_(0)
                ).as_("igst"),
                Sum(
                    Case()
                    .when(
                        boe_taxes.gst_tax_type.isin(["cess", "cess_non_advol"]),
                        boe_taxes.tax_amount,
                    )
                    .else_(0)
                ).as_("cess"),
                Max(IfNull(pi.supplier, "")).as_("party"),
                Max(IfNull(pi.supplier_name, "")).as_("party_name"),
                Max(IfNull(pi.supplier_gstin, "")).as_("party_gstin"),
                Max(IfNull(pi_item.is_fixed_asset, 0)).as_("is_fixed_asset"),
            )
            .where(
                (boe.company == self.company)
                & (boe.company_gstin == self.company_gstin)
                & (boe.docstatus == 1)
                & (boe.posting_date.between(self.from_date, self.to_date))
            )
            .groupby(boe.name, boe.posting_date, boe.total_taxable_value)
        ).run(as_dict=True)

        inputs, capital_goods = {}, {}
        for row in rows:
            is_cg = bool(flt(row.is_fixed_asset))
            taxable_value = flt(row.taxable_value)
            igst = flt(row.igst)
            cess = flt(row.cess)
            invoice_dict = {
                "document_number": row.document_number,
                "document_date": str(row.posting_date),
                "supplier_gstin": row.party_gstin or "",
                "supplier_name": row.party_name or "",
                "gst_category": "Overseas",
                "place_of_supply": "",
                "reverse_charge": "N",
                "transaction_type": "Bill of Entry",
                "document_value": taxable_value + igst + cess,
                "itc_classification": "Import Of Goods",
                "doc_route": "bill-of-entry",
                "items": [
                    {
                        "taxable_value": taxable_value,
                        "igst_amount": igst,
                        "cgst_amount": 0.0,
                        "sgst_amount": 0.0,
                        "cess_amount": cess,
                        "tax_rate": 0.0,
                    }
                ],
                "total_taxable_value": taxable_value,
                "total_igst_amount": igst,
                "total_cgst_amount": 0.0,
                "total_sgst_amount": 0.0,
                "total_cess_amount": cess,
            }
            target = capital_goods if is_cg else inputs
            target[row.document_number] = invoice_dict

        return {
            GSTR9_Row.TABLE_6E_INPUTS: inputs,
            GSTR9_Row.TABLE_6E_CAPITAL_GOODS: capital_goods,
        }

    # ────────────────────────────────────────────────────────
    # Internal: Advances (Table 4F)
    # ────────────────────────────────────────────────────────

    def _get_advances_data(self):
        """
        Get net advances (received minus adjusted) for the entire FY.
        Reuses GSTR-1 advance query logic (GSTR11A11BData).
        """
        from india_compliance.gst_india.utils import get_gst_accounts_by_type
        from india_compliance.gst_india.utils.gstr_1.gstr_1_data import GSTR11A11BData

        result = _empty_row()
        gst_accounts = get_gst_accounts_by_type(self.company, "Output")

        filters = frappe._dict(
            company=self.company,
            company_gstin=self.company_gstin,
            from_date=self.from_date,
            to_date=self.to_date,
        )

        adv_data = GSTR11A11BData(filters, gst_accounts)

        for method, multiplier in (("get_11A_query", 1), ("get_11B_query", -1)):
            rows = getattr(adv_data, method)().run(as_dict=True)

            for row in rows:
                is_intra = row.get("place_of_supply", "")[:2] == self.company_gstin[:2]
                tax_amount = flt(row.get("tax_amount", 0)) * multiplier

                result["taxable_value"] += flt(row.get("taxable_value", 0)) * multiplier
                result["igst"] += 0 if is_intra else tax_amount
                result["cgst"] += (tax_amount / 2) if is_intra else 0
                result["sgst"] += (tax_amount / 2) if is_intra else 0
                result["cess"] += flt(row.get("cess_amount", 0)) * multiplier

        return result


class GSTR9OutwardClassifier:
    """
    Classifies outward supply (Sales Invoice) items into GSTR-9 row keys.

    Reuses the GSTR-1 pattern of per-item Python conditions with
    cache_invoice_condition for deduplication within a single item row.
    """

    def classify(self, item):
        """Returns the GSTR-9 row key for an outward sales invoice item."""
        self.invoice_conditions = {}

        is_forward = self.is_forward(item)
        is_b2c = self.is_b2c(item)

        # ── B2C ──
        if is_b2c:
            # CN/DN: all items to 4A; Forward: only taxable items to 4A
            if not is_forward or not self.is_non_taxable_item(item):
                return GSTR9_Row.TABLE_4A

            # B2C forward non-taxable items fall through to 5D/5E/5F below

        # ── Credit Notes (non-B2C) ──
        if self.is_cn(item):
            if self.is_taxable_category(item) and not self.is_non_taxable_item(item):
                return GSTR9_Row.TABLE_4I

            return GSTR9_Row.TABLE_5H

        # ── Debit Notes (non-B2C) ──
        if self.is_dn(item):
            if self.is_taxable_category(item) and not self.is_non_taxable_item(item):
                return GSTR9_Row.TABLE_4J

            return GSTR9_Row.TABLE_5I

        # ── Forward invoices: non-taxable items by gst_treatment ──
        if self.is_exempted(item):
            return GSTR9_Row.TABLE_5D

        if self.is_nil_rated(item):
            return GSTR9_Row.TABLE_5E

        if self.is_non_gst(item):
            return GSTR9_Row.TABLE_5F

        # ── Forward invoices: taxable items by gst_category ──
        cat = item.gst_category
        has_gstin = self.has_gstin(item)

        if (
            cat in ("Registered Regular", "UIN Holders")
            and has_gstin
            and not item.is_reverse_charge
        ):
            return GSTR9_Row.TABLE_4B

        if cat == "Overseas":
            if item.is_export_with_gst:
                return GSTR9_Row.TABLE_4C
            return GSTR9_Row.TABLE_5A

        if cat == "SEZ":
            if item.is_export_with_gst and not item.is_reverse_charge:
                return GSTR9_Row.TABLE_4D
            if not item.is_export_with_gst:
                return GSTR9_Row.TABLE_5B

        if cat == "Deemed Export":
            return GSTR9_Row.TABLE_4E

        if item.is_reverse_charge and not item.ecommerce_gstin:
            return GSTR9_Row.TABLE_5C

        if self.is_ecom_sec95(item):
            return GSTR9_Row.TABLE_5C1

        return None

    # ── Conditions (reuses cache_invoice_condition from GSTR-1) ──

    @cache_invoice_condition
    def is_nil_rated(self, item):
        return item.gst_treatment == "Nil-Rated"

    @cache_invoice_condition
    def is_exempted(self, item):
        return item.gst_treatment == "Exempted"

    @cache_invoice_condition
    def is_non_gst(self, item):
        return item.gst_treatment == "Non-GST"

    @cache_invoice_condition
    def is_non_taxable_item(self, item):
        return (
            self.is_nil_rated(item) or self.is_exempted(item) or self.is_non_gst(item)
        )

    @cache_invoice_condition
    def is_cn(self, item):
        return bool(item.is_return)

    @cache_invoice_condition
    def is_dn(self, item):
        return bool(item.is_debit_note)

    @cache_invoice_condition
    def is_forward(self, item):
        return not self.is_cn(item) and not self.is_dn(item)

    @cache_invoice_condition
    def has_gstin(self, item):
        return bool(item.billing_address_gstin)

    @cache_invoice_condition
    def is_ecom_sec95(self, item):
        return bool(item.ecommerce_gstin) and bool(item.is_reverse_charge)

    @cache_invoice_condition
    def is_b2c(self, item):
        return item.gst_category == "Unregistered" and not self.is_ecom_sec95(item)

    @cache_invoice_condition
    def is_taxable_category(self, item):
        """Invoice-level check: is the supply category one where tax is payable."""
        return (
            (
                item.gst_category in ("Registered Regular", "UIN Holders")
                and self.has_gstin(item)
                and not item.is_reverse_charge
            )
            or (item.gst_category == "Overseas" and item.is_export_with_gst)
            or (item.gst_category == "SEZ" and item.is_export_with_gst)
            or item.gst_category == "Deemed Export"
        )


class GSTR9PurchaseClassifier:
    """
    Classifies Purchase Invoice items into GSTR-9 row keys for
    Table 4G (RCM tax liability) and Table 6 (ITC availed).

    A single item can contribute to BOTH 4G and a Table 6 row.
    """

    def __init__(self, company_gstin):
        self.company_gstin = company_gstin

    def classify(self, item):
        """
        Returns (rcm_key, itc_key) — either can be None.

        rcm_key: GSTR9_Row.TABLE_4G if the invoice is reverse charge.
        itc_key: Table 6 sub-row based on itc_classification + item type.
        """
        rcm_key = GSTR9_Row.TABLE_4G if item.is_reverse_charge else None
        itc_key = self._get_itc_row_key(item)

        return rcm_key, itc_key

    def _get_itc_row_key(self, item):
        cls = item.itc_classification
        if not cls:
            return None

        if self.company_gstin == (item.supplier_gstin or ""):
            return None

        if item.ineligibility_reason == "ITC restricted due to PoS rules":
            return None

        is_cg = bool(item.is_fixed_asset)
        is_service = not item.is_fixed_asset and not item.is_stock_item

        if cls == "Import Of Service":
            return GSTR9_Row.TABLE_6F

        if cls == "Input Service Distributor":
            return GSTR9_Row.TABLE_6G

        has_gstin = bool(item.supplier_gstin)

        if cls == "ITC on Reverse Charge":
            if has_gstin:
                if is_cg:
                    return GSTR9_Row.TABLE_6D_CAPITAL_GOODS
                if is_service:
                    return GSTR9_Row.TABLE_6D_INPUT_SERVICES
                return GSTR9_Row.TABLE_6D_INPUTS

            if is_cg:
                return GSTR9_Row.TABLE_6C_CAPITAL_GOODS
            if is_service:
                return GSTR9_Row.TABLE_6C_INPUT_SERVICES
            return GSTR9_Row.TABLE_6C_INPUTS

        if cls == "Import Of Goods":
            # ITC for import of goods is claimed via Bill of Entry (BOE), not the PI.
            return None

        if cls == "All Other ITC":
            if is_cg:
                return GSTR9_Row.TABLE_6B_CAPITAL_GOODS
            if is_service:
                return GSTR9_Row.TABLE_6B_INPUT_SERVICES
            return GSTR9_Row.TABLE_6B_INPUTS

        return None


def _get_transaction_type(item, is_purchase):
    """Determine transaction type string from invoice flags."""
    if getattr(item, "is_return", False):
        return "Return" if is_purchase else "Credit Note"
    if getattr(item, "is_debit_note", False):
        return "Debit Note"
    return "Bill" if is_purchase else "Invoice"


def _accumulate_item(
    accumulator,
    row_key,
    document_number,
    item,
    party_name_field,
    party_gstin_field,
    party_gstin_key,
    is_purchase=False,
    extra_fields=None,
):
    """
    Accumulate item-level amounts into per-(row_key, invoice) dicts.

    Produces GSTR-1-style invoice dicts with an `items` list for per-item
    tax breakdown and `total_*_amount` fields for invoice-level aggregates.
    Multiple items from the same invoice going to the same row_key are
    appended to the `items` list and summed into the totals.
    """
    acc_key = (row_key, document_number)

    if acc_key not in accumulator:
        document_value = (
            flt(item.base_rounded_total)
            if flt(item.base_rounded_total)
            else flt(item.base_grand_total)
        )
        entry = {
            "document_number": document_number,
            "document_date": str(item.posting_date),
            party_gstin_key: getattr(item, party_gstin_field, "") or "",
            party_name_field: getattr(item, party_name_field, ""),
            "gst_category": item.gst_category,
            "place_of_supply": getattr(item, "place_of_supply", "") or "",
            "reverse_charge": "Y" if item.is_reverse_charge else "N",
            "transaction_type": _get_transaction_type(item, is_purchase),
            "document_value": document_value,
            "shipping_bill_number": getattr(item, "shipping_bill_number", "") or "",
            "shipping_bill_date": str(getattr(item, "shipping_bill_date", "") or ""),
            "port_code": getattr(item, "port_code", "") or "",
            "items": [],
            "total_taxable_value": 0.0,
            "total_igst_amount": 0.0,
            "total_cgst_amount": 0.0,
            "total_sgst_amount": 0.0,
            "total_cess_amount": 0.0,
        }
        if extra_fields:
            entry.update(extra_fields)
        accumulator[acc_key] = entry

    entry = accumulator[acc_key]

    tax_rate = flt(getattr(item, "tax_rate", 0))
    taxable_value = flt(item.taxable_value)
    igst_amount = flt(item.igst)
    cgst_amount = flt(item.cgst)
    sgst_amount = flt(item.sgst)
    cess_amount = flt(item.cess)

    # Group items by tax_rate — same rate merges into one item entry (GSTR-1 pattern)
    existing = next((i for i in entry["items"] if i["tax_rate"] == tax_rate), None)
    if existing:
        existing["taxable_value"] += taxable_value
        existing["igst_amount"] += igst_amount
        existing["cgst_amount"] += cgst_amount
        existing["sgst_amount"] += sgst_amount
        existing["cess_amount"] += cess_amount
    else:
        item_dict = {
            "taxable_value": taxable_value,
            "igst_amount": igst_amount,
            "cgst_amount": cgst_amount,
            "sgst_amount": sgst_amount,
            "cess_amount": cess_amount,
            "tax_rate": tax_rate,
        }
        if extra_fields and "itc_classification" in extra_fields:
            item_dict["itc_classification"] = extra_fields["itc_classification"]
        entry["items"].append(item_dict)

    entry["total_taxable_value"] += taxable_value
    entry["total_igst_amount"] += igst_amount
    entry["total_cgst_amount"] += cgst_amount
    entry["total_sgst_amount"] += sgst_amount
    entry["total_cess_amount"] += cess_amount


def _build_result(accumulator):
    """
    Convert the flat accumulator dict keyed by (row_key, invoice_name)
    into {row_key: {invoice_name: invoice_dict}} — the same nested-dict
    format used by GSTR-1 books data.
    """
    result = {}
    for (row_key, doc_num), inv_data in accumulator.items():
        result.setdefault(row_key, {})[doc_num] = inv_data

    return result
