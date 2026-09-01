"""Large invoices to unregistered buyers (table 5). Portal groups by place of supply."""

from india_compliance.gst_returns.fields.gstr1 import DocField as doc
from india_compliance.gst_returns.fields.gstr1 import ItemField as item
from india_compliance.gst_returns.fields.gstr1 import RawField as raw
from india_compliance.gst_returns.fields.gstr1 import SubCategory

from . import _shared as s

SUBCATEGORY = SubCategory.B2CL.value

KEYS = {
    raw.FLAG: doc.FLAG,
    raw.DOC_NUMBER: doc.DOC_NUMBER,
    raw.DOC_DATE: doc.DOC_DATE,
    raw.DOC_VALUE: doc.DOC_VALUE,
    raw.DIFF_PERCENTAGE: doc.DIFF_PERCENTAGE,
    raw.ITEMS: doc.ITEMS,
    raw.ITEM_DETAILS: item.ITEM_DETAILS,
    raw.TAX_RATE: item.TAX_RATE,
    raw.TAXABLE_VALUE: item.TAXABLE_VALUE,
    raw.IGST: item.IGST,
    raw.CESS: item.CESS,
}

SUBCATEGORIES = (SUBCATEGORY,)

ITEM_DEFAULTS = dict.fromkeys(s.ITEM_TOTALS_IGST, 0)

MONEY = (raw.DOC_VALUE, raw.DIFF_PERCENTAGE)
ITEM_MONEY = (raw.TAXABLE_VALUE, raw.IGST, raw.CESS)


def to_canonical(gov_data):
    output = {}

    def state(group):
        return {
            doc.POS: s.pos_from_gov(group.get(raw.POS)),
            doc.DOC_TYPE: SUBCATEGORY,
            doc.ERROR_CD: group.get(raw.ERROR_CD),
            doc.ERROR_MSG: group.get(raw.ERROR_MSG),
        }

    def read(invoice, header):
        row = s.drop_flag(s.with_defaults(s.pick(invoice, KEYS), header))

        s.convert(row, doc.DOC_DATE, s.date_from_gov)
        s.convert(row, doc.ITEMS, lambda items: s.wrapped_items_from_gov(items, KEYS, ITEM_DEFAULTS))
        s.add_item_totals(row, row.get(doc.ITEMS), s.ITEM_TOTALS_IGST)

        return row

    for row in s.rows_from_groups(gov_data, raw.INVOICES, state, read):
        output[row[doc.DOC_NUMBER]] = row

    return {SUBCATEGORY: output}


def from_books(grouped_rows):
    """Books rows -> one row per invoice, for the subcategories this category reports."""
    return s.invoice_rows_from_books(grouped_rows, SUBCATEGORIES)


def to_gov(rows, company_gstin=""):
    def write(row):
        out = s.round_money(s.pick_back(row, KEYS), MONEY)

        s.convert(out, raw.DOC_DATE, s.date_to_gov)
        s.convert(out, raw.ITEMS, lambda items: s.wrapped_items_to_gov(items, KEYS, ITEM_MONEY))

        return s.drop_zero_diff(out)

    return s.groups_from_rows(
        rows,
        group_key=lambda row: row[doc.POS],
        group_header=lambda row: {raw.POS: s.pos_to_gov(row[doc.POS])},
        rows_field=raw.INVOICES,
        write_row=write,
    )
