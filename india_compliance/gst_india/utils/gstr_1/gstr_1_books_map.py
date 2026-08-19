"""Map books data (invoices, advances, document ranges) into the canonical GSTR-1 shape."""

from collections import defaultdict

import frappe
from frappe.utils import cint, flt

from india_compliance.gst_india.utils import (
    MONTHS,
    get_gst_accounts_by_type,
    get_party_for_gstin,
)
from india_compliance.gst_india.utils.gstr_1 import (
    Category,
    SubCategory,
)
from india_compliance.gst_india.utils.gstr_1.gstr_1_data import (
    GSTR1DocumentIssuedSummary,
    GSTR1Invoices,
    GSTR11A11BData,
)
from india_compliance.gst_india.utils.gstr_1.sections import _shared as s
from india_compliance.gst_india.utils.gstr_1.sections import (
    advances,
    b2b,
    b2cl,
    b2cs,
    cdnr,
    cdnur,
    doc_issue,
    exports,
    hsn,
    nil_rated,
    supecom,
)


class GSTR1BooksData:
    """Books data -> canonical GSTR-1.

    Queries the invoices, hands the rows to each category to build its own, and reports what
    rounding cost. Row building itself lives with the category, in `sections/`.
    """

    def __init__(self, filters):
        self.filters = filters
        if filters.get("month_or_quarter"):
            self.current_month = MONTHS.index(filters.month_or_quarter) + 1

    def update_rounding_difference(self, prepared_data, lost_to_rounding):
        """Report what settling the amounts cost.

        Reported under the invoice total names, because the page offers to post a journal entry
        from these figures -- that is how the residual gets back into the ledger.
        """
        # never None -- flt without a precision rounds nothing, and float dust reads as a real residual
        precision = cint(frappe.db.get_default("currency_precision")) or 2
        reported_as = s.flip(s.BOOKS_COLUMNS)

        # an amount with no invoice total to sit under keeps its own name rather than raising here
        difference = {
            reported_as.get(column, column): flt(value, precision)
            for column, value in lost_to_rounding.items()
        }

        # saved as object -> it's normalized
        prepared_data["rounding_difference"] = {"rounding_difference": difference}

    def prepare_mapped_data(self):
        prepared_data = {}

        _class = GSTR1Invoices(self.filters)
        data = _class.get_invoices_for_item_wise_summary()
        _class.process_invoices(data)  # amounts come back settled to two decimals

        hsn_rows, invoice_rows, nil_rows, b2cs_rows, supecom_rows = self.get_structured_data(data)

        # each category takes the rows it reports and builds them its own way
        for section in (b2b, b2cl, exports, cdnr, cdnur):
            prepared_data.update(section.from_books(invoice_rows))

        prepared_data.update(nil_rated.from_books(nil_rows))
        prepared_data.update(b2cs.from_books(b2cs_rows))
        prepared_data.update(supecom.from_books(supecom_rows, self.operator_name))

        for category, rows in {
            Category.AT.value: self.prepare_advances_recevied_data(),
            Category.TXP.value: self.prepare_advances_adjusted_data(),
            Category.DOC_ISSUE.value: self.prepare_document_issued_data(),
            **hsn.from_books(hsn_rows, self.hsn_descriptions(hsn_rows).get),
        }.items():
            if rows:
                prepared_data[category] = rows

        self.process_for_quarterly(prepared_data)

        self.update_rounding_difference(prepared_data, _class.rounding_difference)

        return prepared_data

    def prepare_hsn_data(self, invoices):
        hsn_rows, *_ = self.get_structured_data(invoices, only_for_hsn=True)

        return hsn.from_books(hsn_rows, self.hsn_descriptions(hsn_rows).get)

    def hsn_descriptions(self, hsn_rows):
        """Descriptions for the product codes this return reports, and no others."""
        codes = {row.gst_hsn_code for by_key in hsn_rows.values() for rows in by_key.values() for row in rows}

        return frappe._dict(
            frappe.get_all(
                "GST HSN Code",
                fields=["name", "description"],
                filters={"name": ("in", list(codes))},
                as_list=True,
            )
        )

    def operator_name(self, gstin):
        """Supplier behind an e-commerce GSTIN, looked up once per return."""
        if not hasattr(self, "_operator_names"):
            self._operator_names = {}

        if gstin not in self._operator_names:
            self._operator_names[gstin] = get_party_for_gstin(gstin, "Supplier") or ""

        return self._operator_names[gstin]

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

            # an empty line, not merely one with no taxable value -- a line can carry tax without
            # it, and dropping such a line takes tax out of the return while HSN still counts it
            if only_for_hsn or not any(item.get(field) for field in GSTR1Invoices.AMOUNT_FIELDS):
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
        return doc_issue.from_books(GSTR1DocumentIssuedSummary(self.filters).get_data())

    def prepare_advances_recevied_data(self):
        return self.prepare_advances_received_or_adjusted_data("Advances")

    def prepare_advances_adjusted_data(self):
        return self.prepare_advances_received_or_adjusted_data("Adjustment")

    def prepare_advances_received_or_adjusted_data(self, type_of_business):
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

        return advances.from_books(query.run(as_dict=True), multipler)

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

        included = data.setdefault("already_included_docs_for_quarterly", [])

        for category in categories_to_process:
            for key, row in data[category].copy().items():
                if key in included_docs:
                    continue

                row["sub_category"] = category
                included.append(row)
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
