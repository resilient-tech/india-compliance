# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe.query_builder import Case
from frappe.query_builder.functions import IfNull
from frappe.utils import flt

from india_compliance.gst_india.utils.gstr3b.gstr3b_data import GSTR3BQuery
from india_compliance.gst_india.utils.gstr_1.gstr_1_data import GSTR1Query
from india_compliance.gst_india.utils.gstr_9 import (
    GSTR9_Row,
    _empty_row,
)


class GSTR9BooksData(GSTR1Query, GSTR3BQuery):
    """
    Computes GSTR-9 books data from ERP transactions for a given company, GSTIN, and financial year.

    Returns classified invoice-level data (books format):
      {row_key: {doc_number: invoice_dict}}  — for drillable rows (GSTR-1 style)
      {row_key: {amount_fields}}             — for manual/aggregated-only rows
      {row_key: special_structure}           — for Tables 14, 15, 17, 18
    """

    def __init__(self, filters):
        """Initialize DocType refs and common filter attributes."""
        self.filters = frappe._dict(filters or {})
        self.si = frappe.qb.DocType("Sales Invoice")
        self.si_item = frappe.qb.DocType("Sales Invoice Item")
        self.si_taxes = frappe.qb.DocType("Sales Taxes and Charges")
        self.additional_si_columns = []
        self.additional_si_item_columns = []
        # GSTR3BQuery attrs
        self.PI = frappe.qb.DocType("Purchase Invoice")
        self.PI_ITEM = frappe.qb.DocType("Purchase Invoice Item")
        self.BOE = frappe.qb.DocType("Bill of Entry")
        self.BOE_ITEM = frappe.qb.DocType("Bill of Entry Item")
        self.filters.filter_by = "Posting Date"
        self.company = self.filters.company
        self.company_gstin = self.filters.company_gstin
        self.from_date = self.filters.from_date
        self.to_date = self.filters.to_date

    def get_query_with_common_filters(self, query, doc=None):
        if doc is None:
            return GSTR1Query.get_query_with_common_filters(self, query)
        return GSTR3BQuery.get_query_with_common_filters(self, query, doc)

    def get_data(self):
        """Return books data."""
        data = {}

        data.update(self._get_classified_outward_supplies())
        data.update(self._get_classified_purchase_invoices())

        for row_key, records in self._get_boe_books().items():
            if records:
                data.setdefault(row_key, {}).update(records)

        data[GSTR9_Row.TABLE_4F] = self._get_advances_data()

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
        into goods (HSN not starting with '99') and services.
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

        rows = get_outward_hsn_data(filters) if direction == "outward" else get_inward_hsn_data(filters)

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
            (services if str(row.get("hsn_code") or "").startswith("99") else goods).append(mapped)

        return {"goods": goods, "services": services}

    # ────────────────────────────────────────────────────────
    # Outward Supplies — Tables 4 & 5
    # ────────────────────────────────────────────────────────

    def _get_classified_outward_supplies(self):
        """
        Fetch all Sales Invoice items in a single query and classify into GSTR-9 rows.

        Returns {row_key: [invoice_dicts]}.
        """
        query = self._get_outward_items_query()
        classifier = GSTR9SalesClassifier()
        accumulator = {}

        with frappe.db.unbuffered_cursor():
            for item in frappe.db.sql(query.get_sql(), as_dict=True, as_iterator=True):
                row_key = classifier.classify(item)
                if not row_key:
                    continue

                self._accumulate_item(
                    accumulator,
                    row_key,
                    item.invoice_no,
                    item,
                    party_name_field="customer_name",
                    party_gstin_field="billing_address_gstin",
                    party_gstin_key="customer_gstin",
                    is_purchase=False,
                )

        return self._build_result(accumulator)

    def _get_outward_items_query(self):
        return self.get_base_query()

    # ────────────────────────────────────────────────────────
    # Purchase Invoices — Table 4G & Table 6
    # ────────────────────────────────────────────────────────

    def _get_classified_purchase_invoices(self):
        """
        Fetch all relevant Purchase Invoice items, classify for Table 4G and Table 6.

        Returns {row_key: [invoice_dicts]}.
        """
        query = self._get_purchase_items_query()
        classifier = GSTR9PurchaseClassifier(self.company_gstin)
        accumulator = {}

        with frappe.db.unbuffered_cursor():
            for item in frappe.db.sql(query.get_sql(), as_dict=True, as_iterator=True):
                rcm_key, itc_key = classifier.classify(item)

                if rcm_key:
                    self._accumulate_item(
                        accumulator,
                        rcm_key,
                        item.voucher_no,
                        item,
                        party_name_field="supplier_name",
                        party_gstin_field="supplier_gstin",
                        party_gstin_key="supplier_gstin",
                        is_purchase=True,
                    )

                if itc_key:
                    self._accumulate_item(
                        accumulator,
                        itc_key,
                        item.voucher_no,
                        item,
                        party_name_field="supplier_name",
                        party_gstin_field="supplier_gstin",
                        party_gstin_key="supplier_gstin",
                        is_purchase=True,
                        extra_fields={"itc_classification": item.itc_classification},
                    )

        return self._build_result(accumulator)

    def _get_purchase_items_query(self):
        item_doc = frappe.qb.DocType("Item")
        return (
            self.get_base_purchase_query()
            .left_join(item_doc)
            .on(item_doc.name == self.PI_ITEM.item_code)
            .select(
                self.PI.supplier,
                self.PI.supplier_name,
                self.PI.is_return,
                self.PI.is_reverse_charge,
                Case()
                .when(self.PI.base_rounded_total != 0, self.PI.base_rounded_total)
                .else_(self.PI.base_grand_total)
                .as_("invoice_total"),
                self.PI_ITEM.is_fixed_asset,
                IfNull(item_doc.is_stock_item, 1).as_("is_stock_item"),
            )
        )

    def _get_boe_books(self):
        """
        Bill of Entry records classified into 6E Inputs / 6E Capital Goods.

        Extends the GSTR-3B BOE base query with supplier info from linked
        Purchase Invoices, then aggregates per-item rows into per-BOE invoice
        dicts in Python.

        Returns {TABLE_6E_INPUTS: {...}, TABLE_6E_CAPITAL_GOODS: {...}}.
        """
        rows = (
            self.get_base_boe_query()
            .left_join(self.PI)
            .on(
                (self.PI.name == self.BOE_ITEM.purchase_invoice)
                & (IfNull(self.BOE_ITEM.purchase_invoice, "") != "")
            )
            .left_join(self.PI_ITEM)
            .on(self.BOE_ITEM.pi_detail == self.PI_ITEM.name)
            .select(
                IfNull(self.PI.supplier_name, "").as_("supplier_name"),
                IfNull(self.PI.supplier_gstin, "").as_("supplier_gstin"),
                IfNull(self.PI_ITEM.is_fixed_asset, 0).as_("is_fixed_asset"),
                IfNull(self.PI.gst_category, "Overseas").as_("gst_category"),
            )
        ).run(as_dict=True)

        # Aggregate per BOE in Python (base query is per BOE_ITEM)
        boe_agg = {}
        for row in rows:
            entry = boe_agg.setdefault(
                row.voucher_no,
                frappe._dict(
                    document_number=row.voucher_no,
                    posting_date=row.posting_date,
                    supplier_gstin=row.supplier_gstin or "",
                    supplier_name=row.supplier_name or "",
                    gst_category=row.gst_category or "Overseas",
                    is_fixed_asset=flt(row.is_fixed_asset),
                    taxable_value=0.0,
                    igst=0.0,
                    cess=0.0,
                ),
            )
            entry.taxable_value += flt(row.taxable_value)
            entry.igst += flt(row.igst_amount)
            entry.cess += flt(row.cess_amount)

        inputs, capital_goods = {}, {}
        for row in boe_agg.values():
            is_cg = bool(row.is_fixed_asset)
            taxable_value = row.taxable_value
            igst = row.igst
            cess = row.cess
            invoice_dict = {
                "document_number": row.document_number,
                "document_date": str(row.posting_date),
                "supplier_gstin": row.supplier_gstin,
                "supplier_name": row.supplier_name,
                "gst_category": row.gst_category,
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
        Returns drillable advances data for Table 4F as {key: invoice_dict}.

        Produces two separate visible entries per Payment Entry when the same PE
        appears in both 11A (Advance Received) and 11B (Advance Adjusted):
          - key "{pe_name}::rcv"  → transaction_type="Advance Received"
          - key "{pe_name}::adj"  → transaction_type="Advance Adjusted"

        Both entries carry doc_route="payment-entry" so the drill-down link
        opens the Payment Entry, not a sales/purchase invoice.
        Reuses GSTR-1 advance query logic (GSTR11A11BData).
        """
        from india_compliance.gst_india.utils import get_gst_accounts_by_type
        from india_compliance.gst_india.utils.gstr_1.gstr_1_data import GSTR11A11BData

        gst_accounts = get_gst_accounts_by_type(self.company, "Output")
        filters = frappe._dict(
            company=self.company,
            company_gstin=self.company_gstin,
            from_date=self.from_date,
            to_date=self.to_date,
        )

        adv_data = GSTR11A11BData(filters, gst_accounts)
        pe = adv_data.pe

        # 11A — one row per PE (already grouped by pe.name in get_11A_query)
        rows_11a = (
            adv_data.get_11A_query()
            .select(pe.name, pe.posting_date, pe.party_name)
            .groupby(pe.posting_date, pe.party_name)
            .run(as_dict=True)
        )

        # 11B — one row per pe_ref allocation; collapse into one entry per PE in Python
        rows_11b_raw = (
            adv_data.get_11B_query()
            .select(pe.name, pe.posting_date, pe.party_name)
            .groupby(pe.name, pe.posting_date, pe.party_name)
            .run(as_dict=True)
        )

        pe_11b = {}
        for row in rows_11b_raw:
            entry = pe_11b.setdefault(
                row.name,
                frappe._dict(
                    name=row.name,
                    posting_date=row.posting_date,
                    party_name=row.party_name,
                    place_of_supply=row.get("place_of_supply") or "",
                    taxable_value=0.0,
                    tax_amount=0.0,
                    cess_amount=0.0,
                ),
            )
            entry.taxable_value += flt(row.taxable_value)
            entry.tax_amount += flt(row.tax_amount)
            entry.cess_amount += flt(row.cess_amount)

        def _make_entry(row, transaction_type, multiplier=1):
            is_intra = (row.get("place_of_supply") or "")[:2] == self.company_gstin[:2]
            tax_amount = flt(row.tax_amount) * multiplier
            taxable_value = flt(row.taxable_value) * multiplier
            cess = flt(row.cess_amount) * multiplier
            igst = 0.0 if is_intra else tax_amount
            cgst = (tax_amount / 2) if is_intra else 0.0
            sgst = (tax_amount / 2) if is_intra else 0.0
            tax_rate = round((tax_amount / taxable_value) * 100) if taxable_value else 0
            return {
                "document_number": row.name,
                "document_date": str(row.posting_date or ""),
                "customer_gstin": "",
                "customer_name": row.get("party_name") or "",
                "gst_category": "",
                "place_of_supply": row.get("place_of_supply") or "",
                "reverse_charge": "N",
                "transaction_type": transaction_type,
                "document_value": taxable_value + igst + cgst + sgst + cess,
                "doc_route": "payment-entry",
                "shipping_bill_number": "",
                "shipping_bill_date": "",
                "port_code": "",
                "items": [
                    {
                        "taxable_value": taxable_value,
                        "igst_amount": igst,
                        "cgst_amount": cgst,
                        "sgst_amount": sgst,
                        "cess_amount": cess,
                        "tax_rate": tax_rate,
                    }
                ],
                "total_taxable_value": taxable_value,
                "total_igst_amount": igst,
                "total_cgst_amount": cgst,
                "total_sgst_amount": sgst,
                "total_cess_amount": cess,
            }

        result = {}
        for row in rows_11a:
            result[f"{row.name}::rcv"] = _make_entry(row, "Advance Received")

        for row in pe_11b.values():
            result[f"{row.name}::adj"] = _make_entry(row, "Advance Adjusted", multiplier=-1)

        return result

    def _get_transaction_type(self, item, is_purchase):
        """Determine transaction type string from invoice flags."""
        if getattr(item, "is_return", False):
            return "Return" if is_purchase else "Credit Note"
        if getattr(item, "is_debit_note", False):
            return "Debit Note"
        return "Bill" if is_purchase else "Invoice"

    def _accumulate_item(
        self,
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
            document_value = flt(item.invoice_total)
            entry = {
                "document_number": document_number,
                "document_date": str(item.posting_date),
                party_gstin_key: getattr(item, party_gstin_field, "") or "",
                party_name_field: getattr(item, party_name_field, ""),
                "gst_category": item.gst_category,
                "place_of_supply": getattr(item, "place_of_supply", "") or "",
                "reverse_charge": "Y" if item.is_reverse_charge else "N",
                "transaction_type": self._get_transaction_type(item, is_purchase),
                "document_value": document_value,
                "shipping_bill_number": getattr(item, "shipping_bill_number", "") or "",
                "shipping_bill_date": str(getattr(item, "shipping_bill_date", "") or ""),
                "port_code": getattr(item, "shipping_port_code", "") or "",
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

        tax_rate = flt(getattr(item, "gst_rate", 0))
        taxable_value = flt(item.taxable_value)
        igst_amount = flt(item.igst_amount)
        cgst_amount = flt(item.cgst_amount)
        sgst_amount = flt(item.sgst_amount)
        cess_amount = flt(item.get("total_cess_amount", item.cess_amount))

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

    def _build_result(self, accumulator):
        """
        Convert the flat accumulator dict keyed by (row_key, invoice_name).

        Returns {row_key: {invoice_name: invoice_dict}} — the same nested-dict
        format used by GSTR-1 books data.
        """
        result = {}
        for (row_key, doc_num), inv_data in accumulator.items():
            result.setdefault(row_key, {})[doc_num] = inv_data

        return result


class GSTR9SalesClassifier:
    """Classifies outward supply (Sales Invoice) items into GSTR-9 row keys."""

    def classify(self, item):
        """Returns the GSTR-9 row key for an outward sales invoice item."""
        if self.is_b2c(item):
            return self._classify_b2c(item)
        if self.is_cn(item):
            return self._classify_cn(item)
        if self.is_dn(item):
            return self._classify_dn(item)
        if self.is_non_taxable_item(item):
            return self._classify_non_taxable_forward(item)
        return self._classify_taxable_forward(item)

    # ── Per-segment classifiers ──

    def _classify_b2c(self, item):
        # CN/DN: all items to 4A; Forward: only taxable items to 4A
        if not self.is_forward(item) or not self.is_non_taxable_item(item):
            return GSTR9_Row.TABLE_4A
        # B2C forward non-taxable → 5D / 5E / 5F
        return self._classify_non_taxable_forward(item)

    def _classify_cn(self, item):
        if self.is_taxable_category(item) and not self.is_non_taxable_item(item):
            return GSTR9_Row.TABLE_4I
        return GSTR9_Row.TABLE_5H

    def _classify_dn(self, item):
        if self.is_taxable_category(item) and not self.is_non_taxable_item(item):
            return GSTR9_Row.TABLE_4J
        return GSTR9_Row.TABLE_5I

    def _classify_non_taxable_forward(self, item):
        if self.is_exempted(item):
            return GSTR9_Row.TABLE_5D
        if self.is_nil_rated(item):
            return GSTR9_Row.TABLE_5E
        if self.is_non_gst(item):
            return GSTR9_Row.TABLE_5F
        return None

    def _classify_taxable_forward(self, item):
        cat = item.gst_category

        if (
            cat in ("Registered Regular", "UIN Holders", "Registered Composition")
            and self.has_gstin(item)
            and not item.is_reverse_charge
        ):
            return GSTR9_Row.TABLE_4B

        if cat == "Overseas":
            return GSTR9_Row.TABLE_4C if item.is_export_with_gst else GSTR9_Row.TABLE_5A

        if cat == "SEZ":
            sez_row = self._classify_sez(item)
            if sez_row is not None:
                return sez_row
            # SEZ + is_export_with_gst + is_reverse_charge falls through to RC check below

        if cat == "Deemed Export":
            return GSTR9_Row.TABLE_4E

        if item.is_reverse_charge and not item.ecommerce_gstin:
            return GSTR9_Row.TABLE_5C

        if self.is_ecom_sec95(item):
            return GSTR9_Row.TABLE_5C1

        return None

    def _classify_sez(self, item):
        if item.is_export_with_gst and not item.is_reverse_charge:
            return GSTR9_Row.TABLE_4D
        if not item.is_export_with_gst:
            return GSTR9_Row.TABLE_5B
        return None

    # ── Conditions ──

    def is_nil_rated(self, item):
        return item.gst_treatment == "Nil-Rated"

    def is_exempted(self, item):
        return item.gst_treatment == "Exempted"

    def is_non_gst(self, item):
        return item.gst_treatment == "Non-GST"

    def is_non_taxable_item(self, item):
        return self.is_nil_rated(item) or self.is_exempted(item) or self.is_non_gst(item)

    def is_cn(self, item):
        return bool(item.is_return)

    def is_dn(self, item):
        return bool(item.is_debit_note)

    def is_forward(self, item):
        return not self.is_cn(item) and not self.is_dn(item)

    def has_gstin(self, item):
        return bool(item.billing_address_gstin)

    def is_ecom_sec95(self, item):
        return bool(item.ecommerce_gstin) and bool(item.is_reverse_charge)

    def is_b2c(self, item):
        return item.gst_category == "Unregistered" and not self.is_ecom_sec95(item)

    def is_taxable_category(self, item):
        """Invoice-level check: is the supply category one where tax is payable."""
        return (
            (
                item.gst_category in ("Registered Regular", "UIN Holders", "Registered Composition")
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
        """Initialize the classifier with the company GSTIN."""
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
        if not self._is_itc_eligible(item):
            return None

        cls = item.itc_classification
        is_cg = bool(item.is_fixed_asset)
        is_service = not item.is_fixed_asset and not item.is_stock_item

        if cls == "Import Of Service":
            return GSTR9_Row.TABLE_6F
        if cls == "Input Service Distributor":
            return GSTR9_Row.TABLE_6G
        if cls == "ITC on Reverse Charge":
            return self._get_rcm_row(item, is_cg, is_service)
        if cls == "Import Of Goods":
            return self._get_import_goods_row(is_cg)
        if cls == "All Other ITC":
            return self._get_all_other_itc_row(is_cg, is_service)

        return None

    def _is_itc_eligible(self, item):
        if not item.itc_classification:
            return False
        if self.company_gstin == (item.supplier_gstin or ""):
            return False
        if item.ineligibility_reason == "ITC restricted due to PoS rules":
            return False
        if item.gst_treatment in ("Nil-Rated", "Exempted", "Non-GST"):
            return False
        return True

    def _get_rcm_row(self, item, is_cg, is_service):
        if bool(item.supplier_gstin):
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

    def _get_import_goods_row(self, is_cg):
        return GSTR9_Row.TABLE_6E_CAPITAL_GOODS if is_cg else GSTR9_Row.TABLE_6E_INPUTS

    def _get_all_other_itc_row(self, is_cg, is_service):
        if is_cg:
            return GSTR9_Row.TABLE_6B_CAPITAL_GOODS
        if is_service:
            return GSTR9_Row.TABLE_6B_INPUT_SERVICES
        return GSTR9_Row.TABLE_6B_INPUTS
