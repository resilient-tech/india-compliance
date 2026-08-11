"""Map books data (invoices, advances, document ranges) into the canonical GSTR-1 shape."""

from collections import defaultdict
from itertools import chain
from typing import ClassVar

import frappe
from frappe.utils import cint, flt

from india_compliance.gst_india.utils import (
    MONTHS,
    get_gst_accounts_by_type,
    get_party_for_gstin,
)
from india_compliance.gst_india.utils.gstr_1 import (
    CATEGORY_SUB_CATEGORY_MAPPING,
    Category,
    DocField,
    ItemField,
    SubCategory,
)
from india_compliance.gst_india.utils.gstr_1.gstr_1_data import (
    GSTR1DocumentIssuedSummary,
    GSTR1Invoices,
    GSTR11A11BData,
)


class BooksDataMapper:
    def get_transaction_type(self, invoice):
        if invoice.is_debit_note:
            return "Debit Note"
        elif invoice.is_return:
            return "Credit Note"
        else:
            return "Invoice"

    def get_category_from_subcategory(self, invoice_sub_category: str) -> Category:
        invoice_sub_category = SubCategory(invoice_sub_category)
        for category, sub_category in CATEGORY_SUB_CATEGORY_MAPPING.items():
            if invoice_sub_category in sub_category:
                return category

    DATA_TO_ITEM_FIELD_MAPPING: ClassVar[dict] = {
        DocField.TAXABLE_VALUE: ItemField.TAXABLE_VALUE,
        DocField.IGST: ItemField.IGST,
        DocField.CGST: ItemField.CGST,
        DocField.SGST: ItemField.SGST,
        DocField.CESS: ItemField.CESS,
    }

    ITEM_TO_INVOICE_FIELD_MAPPING: ClassVar[dict] = {
        ItemField.TAXABLE_VALUE: "taxable_value",
        ItemField.IGST: "igst_amount",
        ItemField.CGST: "cgst_amount",
        ItemField.SGST: "sgst_amount",
        ItemField.CESS: "total_cess_amount",
    }

    DATA_TO_INVOICE_FIELD_MAPPING: ClassVar[dict] = {
        DocField.TAXABLE_VALUE: "taxable_value",
        DocField.IGST: "igst_amount",
        DocField.CGST: "cgst_amount",
        DocField.SGST: "sgst_amount",
        DocField.CESS: "total_cess_amount",
    }

    PRECISION = 2

    def process_data_for_invoice_no_key(self, grouped_data, prepared_data):
        """
        Input:
            grouped_data: {
                (invoice_sub_category, invoice_no): {
                    gst_rate: [invoice_items]
                }
            }
            prepared_data: dict to be updated with the processed data
        """
        if not grouped_data:
            return

        for (sub_category, invoice_no), rate_wise_item in grouped_data.items():
            doc = next(chain(*rate_wise_item.values()))

            if sub_category not in prepared_data:
                prepared_data[sub_category] = {}

            sub_category_dict = prepared_data[sub_category]
            sub_category_dict[invoice_no] = {
                # TODO: make a method for creating the dict
                DocField.TRANSACTION_TYPE: self.get_transaction_type(doc),
                DocField.CUST_GSTIN: doc.billing_address_gstin,
                DocField.CUST_NAME: doc.customer_name,
                DocField.DOC_DATE: doc.posting_date,
                DocField.DOC_NUMBER: doc.invoice_no,
                DocField.DOC_VALUE: doc.invoice_total,
                DocField.POS: doc.place_of_supply,
                DocField.REVERSE_CHARGE: ("Y" if doc.is_reverse_charge else "N"),
                DocField.DOC_TYPE: doc.invoice_type,
                **self.get_invoice_values(),
                DocField.DIFF_PERCENTAGE: 0,
                DocField.SHIPPING_PORT_CODE: doc.shipping_port_code,
                DocField.SHIPPING_BILL_NUMBER: doc.shipping_bill_number,
                DocField.SHIPPING_BILL_DATE: doc.shipping_bill_date,
                "items": [],
            }

            invoice = sub_category_dict[invoice_no]

            for gst_rate, items in rate_wise_item.items():
                tax_item = defaultdict(int)

                for item in items:
                    for key, field in self.ITEM_TO_INVOICE_FIELD_MAPPING.items():
                        tax_item[key] += item.get(field, 0)

                tax_item[ItemField.TAX_RATE] = gst_rate
                invoice["items"].append(dict(tax_item))

            # Aggregate the values for each item field with same GST Rate
            # Round off this aggregated value and compute the difference at GST Rate level

            for key, field in self.DATA_TO_ITEM_FIELD_MAPPING.items():
                for item in invoice["items"]:
                    value = item.get(field, 0)
                    rounded = flt(value, self.PRECISION)
                    diff = value - rounded

                    item[field] = rounded
                    invoice[key] += rounded

                    self.rounding_difference[key] += diff

                rounded = flt(invoice[key], self.PRECISION)
                invoice[key] = rounded
                self.invoice_totals[doc.hsn_sub_category][key] += rounded

    def process_data_for_nil_exempt(self, grouped_data, prepared_data):
        """
        Input:
            grouped_data: {
                (invoice_sub_category, invoice_no): {
                    gst_rate: [invoice_items]
                }
            }
            prepared_data: dict to be updated with the processed data
        """
        if not grouped_data:
            return

        sub_category = SubCategory.NIL_EXEMPT.value
        nil_exempt = prepared_data.setdefault(sub_category, {})

        for _, rate_wise_item in grouped_data.items():
            item = next(chain(*rate_wise_item.values()), None)

            if item.invoice_type not in nil_exempt:
                nil_exempt[item.invoice_type] = []

            invoices_by_type = nil_exempt[item.invoice_type]

            invoice = {
                DocField.TRANSACTION_TYPE: self.get_transaction_type(item),
                DocField.CUST_GSTIN: item.billing_address_gstin,
                DocField.CUST_NAME: item.customer_name,
                DocField.DOC_NUMBER: item.invoice_no,
                DocField.DOC_DATE: item.posting_date,
                DocField.DOC_VALUE: item.invoice_total,
                DocField.POS: item.place_of_supply,
                DocField.REVERSE_CHARGE: ("Y" if item.is_reverse_charge else "N"),
                DocField.DOC_TYPE: item.invoice_type,
                DocField.TAXABLE_VALUE: 0,
                DocField.NIL_RATED_AMOUNT: 0,
                DocField.EXEMPTED_AMOUNT: 0,
                DocField.NON_GST_AMOUNT: 0,
            }

            invoices_by_type.append(invoice)

            for item in chain(*rate_wise_item.values()):
                invoice[DocField.TAXABLE_VALUE] += item.taxable_value

                if item.gst_treatment == "Nil-Rated":
                    invoice[DocField.NIL_RATED_AMOUNT] += item.taxable_value

                elif item.gst_treatment == "Exempted":
                    invoice[DocField.EXEMPTED_AMOUNT] += item.taxable_value

                elif item.gst_treatment == "Non-GST":
                    invoice[DocField.NON_GST_AMOUNT] += item.taxable_value

            # Round
            key = DocField.TAXABLE_VALUE
            val = invoice.get(key, 0)
            rounded = flt(val, self.PRECISION)
            diff = val - rounded

            invoice[key] = rounded

            self.rounding_difference[key] += diff
            self.invoice_totals[item.hsn_sub_category][key] += rounded

    def process_data_for_b2cs(self, grouped_data, prepared_data):
        """
        Input:
            grouped_data: {
                (invoice_sub_category, invoice_no): {
                    gst_rate: [invoice_items]
                }
            }
            prepared_data: dict to be updated with the processed data
        """
        if not grouped_data:
            return

        sub_category = Category.B2CS.value
        b2c_others = prepared_data.setdefault(sub_category, {})

        for _, rate_wise_item in grouped_data.items():
            for gst_rate, items in rate_wise_item.items():
                item = items[0]
                key = f"{item.place_of_supply} - {flt(gst_rate)}"

                if key not in b2c_others:
                    b2c_others[key] = []

                invoice_list = b2c_others[key]

                invoice = {
                    DocField.DOC_DATE: item.posting_date,
                    DocField.DOC_NUMBER: item.invoice_no,
                    DocField.DOC_VALUE: item.invoice_total,
                    DocField.CUST_NAME: item.customer_name,
                    # currently other value is not supported in GSTR-1
                    DocField.DOC_TYPE: "OE",
                    DocField.TRANSACTION_TYPE: self.get_transaction_type(item),
                    DocField.POS: item.place_of_supply,
                    DocField.TAX_RATE: item.gst_rate,
                    DocField.ECOMMERCE_GSTIN: item.ecommerce_gstin,
                    **self.get_invoice_values(),
                }

                invoice_list.append(invoice)

                for key, field in self.DATA_TO_INVOICE_FIELD_MAPPING.items():
                    for item in items:
                        invoice[key] += item.get(field, 0)

                    val = invoice.get(key, 0)
                    rounded = flt(val, self.PRECISION)
                    diff = val - rounded

                    invoice[key] = rounded

                    self.rounding_difference[key] += diff
                    self.invoice_totals[item.hsn_sub_category][key] += rounded

    def process_data_for_hsn_summary(self, grouped_data, prepared_data):
        """
        Input:
            grouped_data: {
                invoice_sub_category: {
                    "gst_hsn_code - uom - gst_rate": [invoice_items]
                }
            }
            prepared_data: dict to be updated with the processed data
        """

        data_to_invoice_field_map = {
            **self.DATA_TO_INVOICE_FIELD_MAPPING,
            DocField.QUANTITY: "qty",
        }
        tax_fields = self.DATA_TO_INVOICE_FIELD_MAPPING.keys()

        for sub_category, hsn_key in grouped_data.items():
            sub_category_dict = prepared_data.setdefault(sub_category, {})

            # HSN Descriptions
            hsn_codes = [key.split(" - ")[0] for key in hsn_key]
            descriptions = frappe._dict(
                frappe.get_all(
                    "GST HSN Code",
                    fields=["name", "description"],
                    filters={"name": ["in", hsn_codes]},
                    as_list=True,
                )
            )

            # Map
            for key, items in hsn_key.items():
                item = items[0]

                sub_category_dict[key] = {
                    DocField.DOC_TYPE: sub_category,
                    DocField.HSN_CODE: item.gst_hsn_code,
                    DocField.DESCRIPTION: descriptions.get(item.gst_hsn_code),
                    DocField.UOM: item.uom,
                    DocField.QUANTITY: 0,
                    DocField.TAX_RATE: item.gst_rate,
                    **self.get_invoice_values(),
                }

                invoice = sub_category_dict[key]

                # Aggregate
                for key, field in data_to_invoice_field_map.items():
                    for item in items:
                        invoice[key] += item.get(field, 0)

                    invoice[key] = flt(invoice[key], self.PRECISION)

                doc_value = sum([invoice.get(field, 0) for field in tax_fields])

                invoice[DocField.DOC_VALUE] = flt(doc_value, self.PRECISION)

            if hasattr(self, "invoice_totals"):
                self.adjust_hsn_totals(sub_category, sub_category_dict)

    def process_data_for_supecom(self, grouped_data, prepared_data):
        """
        Aggregate e-commerce supplies by operator GSTIN for each supply type.

        Input:
            grouped_data: {ecommerce_supply_type: {invoice_no: [invoice_items]}}
            prepared_data: dict to be updated with the processed data

        Output structure (before normalize_data):
            {
                SUPECOM_52.value: {eco_gstin: {doc_type, eco_gstin, taxable_value, igst, ...}},
                SUPECOM_9_5.value: {...},
            }
        """
        if not grouped_data:
            return

        def get_party_name_for_gstin(eco_gstin, party_name_map):
            if eco_gstin not in party_name_map:
                party_name_map[eco_gstin] = get_party_for_gstin(eco_gstin, "Supplier") or ""

            return party_name_map[eco_gstin]

        data_to_invoice_field_map = self.DATA_TO_INVOICE_FIELD_MAPPING
        empty_invoice_values = self.get_invoice_values()
        party_name_map = {}

        for supply_type, invoice_wise in grouped_data.items():
            sub_category = prepared_data.setdefault(supply_type, {})

            for items in invoice_wise.values():
                eco_gstin = items[0].get("ecommerce_gstin", "")
                entry = sub_category.setdefault(
                    eco_gstin,
                    {
                        DocField.DOC_TYPE: supply_type,
                        DocField.ECOMMERCE_GSTIN: eco_gstin,
                        DocField.ECOMMERCE_OPERATOR_NAME: get_party_name_for_gstin(eco_gstin, party_name_map),
                        **empty_invoice_values.copy(),
                    },
                )

                invoice_totals = empty_invoice_values.copy()
                for item in items:
                    for key, field in data_to_invoice_field_map.items():
                        invoice_totals[key] += item.get(field, 0)

                for key in data_to_invoice_field_map:
                    entry[key] += flt(invoice_totals[key], self.PRECISION)

            # Round at operator level
            for entry in sub_category.values():
                for key in data_to_invoice_field_map:
                    entry[key] = flt(entry[key], self.PRECISION)

    def process_data_for_document_issued_summary(self, row, prepared_data):
        key = f"{row['nature_of_document']} - {row['from_serial_no']}"

        if key in prepared_data:
            return

        prepared_data[key] = {
            DocField.DOC_TYPE: row["nature_of_document"],
            DocField.FROM_SR: row["from_serial_no"],
            DocField.TO_SR: row["to_serial_no"],
            DocField.TOTAL_COUNT: row["total_issued"],
            DocField.DRAFT_COUNT: row["total_draft"],
            DocField.CANCELLED_COUNT: row["cancelled"],
            DocField.NET_ISSUE: row["total_submitted"],
        }

    def process_data_for_advances_received_or_adjusted(self, row, prepared_data, multiplier=1):
        advances = {}
        tax_rate = round((row["tax_amount"] / row["taxable_value"]) * 100)
        key = f"{row['place_of_supply']} - {flt(tax_rate)}"

        mapped_dict = prepared_data.setdefault(key, [])

        advances[DocField.CUST_NAME] = row["party"]
        advances[DocField.DOC_NUMBER] = row["name"]
        advances[DocField.DOC_DATE] = row["posting_date"]
        advances[DocField.POS] = row["place_of_supply"]
        advances[DocField.TAXABLE_VALUE] = row["taxable_value"] * multiplier
        advances[DocField.TAX_RATE] = tax_rate
        advances[DocField.CESS] = row["cess_amount"] * multiplier

        if row.get("reference_name"):
            advances["against_voucher"] = row["reference_name"]

        if row["place_of_supply"][0:2] == row["company_gstin"][0:2]:
            advances[DocField.CGST] = row["tax_amount"] / 2 * multiplier
            advances[DocField.SGST] = row["tax_amount"] / 2 * multiplier
            advances[DocField.IGST] = 0

        else:
            advances[DocField.IGST] = row["tax_amount"] * multiplier
            advances[DocField.CGST] = 0
            advances[DocField.SGST] = 0

        mapped_dict.append(advances)

    # utils

    def get_invoice_values(self, invoice=None):
        if invoice is None:
            invoice = {}

        return {
            DocField.TAXABLE_VALUE: invoice.get("taxable_value", 0),
            DocField.IGST: invoice.get("igst_amount", 0),
            DocField.CGST: invoice.get("cgst_amount", 0),
            DocField.SGST: invoice.get("sgst_amount", 0),
            DocField.CESS: invoice.get("total_cess_amount", 0),
        }

    def initialize_totals(self):
        """
        Initialize the rounding difference dictionary.
        This method is used to reset the rounding difference.
        """
        self.invoice_totals = defaultdict(lambda: defaultdict(float))
        self.rounding_difference = defaultdict(float)

    def update_rounding_difference(self, prepared_data):
        """
        Round off the rounding difference values to 2 decimal places.
        This method is used to round off the rounding difference values.
        """
        precision = cint(frappe.db.get_default("currency_precision")) or None

        for key, value in self.rounding_difference.items():
            self.rounding_difference[key] = flt(value, precision)

        # saved as object -> it's normalized
        prepared_data["rounding_difference"] = {"rounding_difference": self.rounding_difference}

    def adjust_hsn_totals(self, sub_category, sub_category_dict):
        expected_totals = self.invoice_totals.get(sub_category)
        if not expected_totals:
            return

        # sort -> to ensure adjusted to same row
        hsn_data = sorted(
            sub_category_dict.values(),
            key=lambda item: item.get(DocField.TAXABLE_VALUE, 0),
            reverse=True,
        )

        # diff
        for row in hsn_data:
            for key in expected_totals:
                expected_totals[key] -= row.get(key, 0)

        # adjust totals
        for key, diff in expected_totals.items():
            for row in hsn_data:
                if row.get(key):
                    row[key] = flt(row[key] + diff, self.PRECISION)
                    break


class GSTR1BooksData(BooksDataMapper):
    def __init__(self, filters):
        self.filters = filters
        if filters.get("month_or_quarter"):
            self.current_month = MONTHS.index(filters.month_or_quarter) + 1

    def prepare_mapped_data(self):
        prepared_data = {}

        _class = GSTR1Invoices(self.filters)
        data = _class.get_invoices_for_item_wise_summary()
        _class.process_invoices(data)

        # initialize rounding difference and hsn error
        self.initialize_totals()

        data_for_hsn, data_for_invoice_no_key, data_for_nil_exempt, data_for_b2cs, data_for_supecom = (
            self.get_structured_data(data)
        )

        self.process_data_for_invoice_no_key(data_for_invoice_no_key, prepared_data)
        self.process_data_for_nil_exempt(data_for_nil_exempt, prepared_data)
        self.process_data_for_b2cs(data_for_b2cs, prepared_data)
        self.process_data_for_supecom(data_for_supecom, prepared_data)

        other_categories = {
            Category.AT.value: self.prepare_advances_recevied_data(),
            Category.TXP.value: self.prepare_advances_adjusted_data(),
            Category.DOC_ISSUE.value: self.prepare_document_issued_data(),
        }

        self.process_data_for_hsn_summary(data_for_hsn, other_categories)

        for category, data in other_categories.items():
            if data:
                prepared_data[category] = data

        self.process_for_quarterly(prepared_data)

        self.update_rounding_difference(prepared_data)

        return prepared_data

    def prepare_hsn_data(self, invoices):
        hsn_summary = {}

        data_for_hsn, *_ = self.get_structured_data(invoices, only_for_hsn=True)
        self.process_data_for_hsn_summary(data_for_hsn, hsn_summary)

        return hsn_summary

    def get_structured_data(self, data, only_for_hsn=False):
        """
        Invoices are bifurcated into different categories by invoice sub-category, invoice number and GST Rate.
        - data_for_invoice_no_key: B2B, B2CL, CDNR, CDNUR, etc.
        - data_for_nil_exempt: Nil Rated, Exempted, Non-GST
        - data_for_b2cs: B2CS (B2C Others)
        - data_for_supecom: Supplies through E-commerce Operators (grouped by supply type then operator GSTIN)

        Further all invoices are grouped by HSN code, UOM, and GST rate
        - data_for_hsn: HSN Summary
        """
        data_for_invoice_no_key = defaultdict(lambda: defaultdict(list))
        data_for_nil_exempt = defaultdict(lambda: defaultdict(list))
        data_for_b2cs = defaultdict(lambda: defaultdict(list))
        data_for_supecom = defaultdict(lambda: defaultdict(list))
        data_for_hsn = defaultdict(lambda: defaultdict(list))

        for item in data:
            gst_rate = flt(item.get("gst_rate"))

            hsn_sub_category = item.get("hsn_sub_category")
            if hsn_sub_category:
                hsn_key = f"{item.gst_hsn_code} - {item.uom} - {gst_rate}"
                data_for_hsn[hsn_sub_category][hsn_key].append(item)

            if only_for_hsn or item.get("taxable_value") == 0:
                continue

            key = (item.get("invoice_sub_category"), item.get("invoice_no"))

            invoice_category = Category(item.get("invoice_category"))
            if invoice_category in (
                Category.B2B,
                Category.EXP,
                Category.B2CL,
                Category.CDNR,
                Category.CDNUR,
            ):
                data_for_invoice_no_key[key][gst_rate].append(item)

            elif invoice_category == Category.NIL_EXEMPT:
                data_for_nil_exempt[key][gst_rate].append(item)

            elif invoice_category == Category.B2CS:
                data_for_b2cs[key][gst_rate].append(item)

            # E-commerce invoices are aggregated into SUPECOM: 52/TCS in addition to
            # their primary category (B2B/B2CS), 9(5) exclusively (no primary above).
            if item.get("ecommerce_gstin") and item.get("ecommerce_supply_type"):
                data_for_supecom[item.ecommerce_supply_type][item.invoice_no].append(item)

        return data_for_hsn, data_for_invoice_no_key, data_for_nil_exempt, data_for_b2cs, data_for_supecom

    def prepare_document_issued_data(self):
        doc_issued_data = {}
        data = GSTR1DocumentIssuedSummary(self.filters).get_data()

        for row in data:
            self.process_data_for_document_issued_summary(row, doc_issued_data)

        return doc_issued_data

    def prepare_advances_recevied_data(self):
        return self.prepare_advances_received_or_adjusted_data("Advances")

    def prepare_advances_adjusted_data(self):
        return self.prepare_advances_received_or_adjusted_data("Adjustment")

    def prepare_advances_received_or_adjusted_data(self, type_of_business):
        advances_data = {}
        self.filters.type_of_business = type_of_business
        gst_accounts = get_gst_accounts_by_type(self.filters.company, "Output")
        _class = GSTR11A11BData(self.filters, gst_accounts)

        if type_of_business == "Advances":
            query = _class.get_11A_query()
            fields = (
                _class.pe.name,
                _class.pe.party,
                _class.pe.posting_date,
                _class.pe.company_gstin,
            )
            multipler = 1

        else:
            query = _class.get_11B_query()
            fields = _class.get_11B_payment_entry_fields(
                name="name",
                party="party",
                posting_date="posting_date",
                company_gstin="company_gstin",
                reference_name="reference_name",
            )
            multipler = -1

        query = query.select(*fields)
        data = query.run(as_dict=True)

        for row in data:
            self.process_data_for_advances_received_or_adjusted(row, advances_data, multipler)

        return advances_data

    def process_for_quarterly(self, data):
        if self.filters.filing_preference != "Quarterly":
            return

        is_m3 = self.current_month % 3 == 0
        m1_m2_subcategories = (
            SubCategory.B2B_REGULAR.value,
            SubCategory.B2B_REVERSE_CHARGE.value,
            SubCategory.SEZWP.value,
            SubCategory.SEZWOP.value,
            SubCategory.DE.value,
            SubCategory.CDNR.value,
        )

        if is_m3:
            self.process_included_docs_for_quarterly(data, m1_m2_subcategories)
        else:
            self.process_excluded_docs_for_quarterly(data, m1_m2_subcategories)

    def process_included_docs_for_quarterly(self, data, m1_m2_subcategories):
        if not data or not isinstance(data, dict):
            return

        included_docs = self.get_already_filed_docs(m1_m2_subcategories)

        categories_to_process = [cat for cat in data.keys() if cat in m1_m2_subcategories]

        if not categories_to_process:
            return

        for category in categories_to_process:
            for key, row in data[category].copy().items():
                if key in included_docs:
                    continue

                row["sub_category"] = category
                data.setdefault("already_included_docs_for_quarterly", []).append(row)
                del data[category][key]

    def process_excluded_docs_for_quarterly(self, data, m1_m2_subcategories):
        if not data or not isinstance(data, dict):
            return

        for category in data.copy():
            if category in m1_m2_subcategories:
                continue

            if category in (
                SubCategory.HSN.value,  # Backwards Compatibility
                SubCategory.HSN_B2B.value,
                SubCategory.HSN_B2C.value,
                SubCategory.DOC_ISSUE.value,
            ):
                del data[category]
                continue

            excluded = data.setdefault("excluded_docs_for_quarterly", [])

            for row in data[category].values():
                if isinstance(row, dict):
                    row["sub_category"] = category
                    excluded.append(row)

                elif isinstance(row, list):
                    for item in row:
                        item["sub_category"] = category

                    excluded.extend(row)

            del data[category]

        return data

    def get_already_filed_docs(self, m1_m2_subcategories):
        from india_compliance.gst_india.doctype.gst_return_log.gst_return_log import (
            get_gst_return_log,
        )

        company_gstin = self.filters.company_gstin
        year = self.filters.year

        log_names = [
            f"GSTR1-{(self.current_month - 1):02d}{year}-{company_gstin}",
            f"GSTR1-{(self.current_month - 2):02d}{year}-{company_gstin}",
        ]

        filed_invoices = set()

        for log_name in log_names:
            gstr1_log = get_gst_return_log(
                log_name,
                company=self.filters.company,
                filing_preference=self.filters.filing_preference,
            )

            if not gstr1_log.filed:
                # Extract month number from log_name (format: GSTR1-MMYYYY-GSTIN)
                month_num = int(log_name.split("-")[1][:2])
                new_filters = frappe._dict(self.filters)
                new_filters.month_or_quarter = MONTHS[month_num - 1]
                gstr1_log.generate_gstr1_data(new_filters)

            filed_data = gstr1_log.get_json_for("filed")

            if not filed_data:
                continue

            for category, invoices in filed_data.items():
                if category not in m1_m2_subcategories:
                    continue

                filed_invoices.update(invoices.keys())

        return filed_invoices
