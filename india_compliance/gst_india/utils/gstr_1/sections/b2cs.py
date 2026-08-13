"""Small sales to unregistered buyers (table 7). One total per state and rate."""

from frappe.utils import flt

from india_compliance.gst_returns.fields.gstr1 import DocField as doc
from india_compliance.gst_returns.fields.gstr1 import RawField as raw
from india_compliance.gst_returns.fields.gstr1 import SubCategory

from . import _shared as s

SUBCATEGORY = SubCategory.B2CS.value

KEYS = {
    raw.FLAG: doc.FLAG,
    raw.TAXABLE_VALUE: doc.TAXABLE_VALUE,
    raw.TYPE: doc.DOC_TYPE,
    raw.DIFF_PERCENTAGE: doc.DIFF_PERCENTAGE,
    raw.POS: doc.POS,
    raw.TAX_RATE: doc.TAX_RATE,
    raw.IGST: doc.IGST,
    raw.CGST: doc.CGST,
    raw.SGST: doc.SGST,
    raw.CESS: doc.CESS,
    raw.ERROR_CD: doc.ERROR_CD,
    raw.ERROR_MSG: doc.ERROR_MSG,
}

# the portal's only supported type here; "E" (e-commerce) is not reported separately
OTHER_THAN_ECOMMERCE = "OE"

MONEY = (
    raw.TAXABLE_VALUE,
    raw.DIFF_PERCENTAGE,
    raw.IGST,
    raw.CGST,
    raw.SGST,
    raw.CESS,
)


def group_key(row):
    """Row identity, books against portal. Not stored."""
    return " - ".join((row.get(doc.POS) or "", str(flt(row.get(doc.TAX_RATE, "")))))


def to_canonical(gov_data):
    output = {}

    for entry in gov_data:
        row = s.drop_flag(s.pick(entry, KEYS))
        s.convert(row, doc.POS, s.pos_from_gov)

        output.setdefault(group_key(row), []).append(row)  # keyed "05-Uttarakhand - 5.0"

    return {SUBCATEGORY: output}


def from_books(grouped_rows):
    """Books rows -> one row per invoice per rate, grouped the way the portal totals them.

       {(_, "SINV-1"): {5.0: [item rows]}}
    -> {"B2C (Others)": {"05-Uttarakhand - 5.0": [{total_taxable_value: 110, tax_rate: 5.0}]}}
    """
    output = {}

    for rows_by_rate in grouped_rows.values():
        for rows in rows_by_rate.values():
            first = rows[0]

            row = {
                doc.DOC_DATE: first.posting_date,
                doc.DOC_NUMBER: first.invoice_no,
                doc.DOC_VALUE: first.invoice_total,
                doc.CUST_NAME: first.customer_name,
                doc.DOC_TYPE: OTHER_THAN_ECOMMERCE,
                doc.TRANSACTION_TYPE: s.transaction_type(first),
                doc.POS: first.place_of_supply,
                doc.TAX_RATE: first.gst_rate,
                doc.ECOMMERCE_GSTIN: first.ecommerce_gstin,
                **{total: s.sum_column(rows, column) for total, column in s.BOOKS_COLUMNS.items()},
            }

            output.setdefault(group_key(row), []).append(row)

    # nothing to report means no section at all, not an empty one
    return {SUBCATEGORY: output} if output else {}


def to_gov(rows, company_gstin=""):
    def write(row):
        out = s.round_money(s.pick_back(row, KEYS), MONEY)

        s.convert(out, raw.POS, s.pos_to_gov)
        s.drop_zero_diff(out)

        out[raw.SUPPLY_TYPE] = s.supply_type(out[raw.POS], company_gstin)

        return out

    return [write(row) for row in rows]
