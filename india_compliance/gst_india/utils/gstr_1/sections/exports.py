"""Invoices shipped out of India, grouped by whether tax was paid (table 6A).

We store the portal's own code here, not a label. The readable name is the subcategory.
"""

from india_compliance.gst_returns.fields.gstr1 import DocField as doc
from india_compliance.gst_returns.fields.gstr1 import ItemField as item
from india_compliance.gst_returns.fields.gstr1 import RawField as raw
from india_compliance.gst_returns.fields.gstr1 import SubCategory

from . import _shared as s

KEYS = {
    raw.FLAG: doc.FLAG,
    raw.DOC_NUMBER: doc.DOC_NUMBER,
    raw.DOC_DATE: doc.DOC_DATE,
    raw.DOC_VALUE: doc.DOC_VALUE,
    raw.SHIPPING_PORT_CODE: doc.SHIPPING_PORT_CODE,
    raw.SHIPPING_BILL_NUMBER: doc.SHIPPING_BILL_NUMBER,
    raw.SHIPPING_BILL_DATE: doc.SHIPPING_BILL_DATE,
    raw.ITEMS: doc.ITEMS,
    raw.TAXABLE_VALUE: item.TAXABLE_VALUE,
    raw.TAX_RATE: item.TAX_RATE,
    raw.IGST: item.IGST,
    raw.CESS: item.CESS,
}

# exp_typ -> its subcategory
SUBCATEGORY_OF = {
    "WPAY": SubCategory.EXPWP.value,
    "WOPAY": SubCategory.EXPWOP.value,
}

ITEM_DEFAULTS = dict.fromkeys(s.ITEM_TOTALS_IGST, 0)

MONEY = (raw.DOC_VALUE,)
ITEM_MONEY = (raw.TAXABLE_VALUE, raw.IGST, raw.CESS)


def to_canonical(gov_data):
    output = {}

    # bucket up front, so an empty export type still shows
    for group in gov_data:
        export_type = group.get(raw.EXPORT_TYPE)
        invoices = output.setdefault(
            SUBCATEGORY_OF.get(export_type, export_type), {}
        )  # WPAY -> Export With Payment of Tax

        header = {
            doc.DOC_TYPE: export_type,
            doc.ERROR_CD: group.get(raw.ERROR_CD),
            doc.ERROR_MSG: group.get(raw.ERROR_MSG),
        }

        for invoice in group.get(raw.INVOICES) or []:
            row = s.drop_flag(s.with_defaults(s.pick(invoice, KEYS), header))

            s.convert(row, doc.DOC_DATE, s.date_from_gov)
            s.convert(row, doc.SHIPPING_BILL_DATE, s.date_from_gov)
            s.convert(row, doc.ITEMS, lambda items: s.flat_items_from_gov(items, KEYS, ITEM_DEFAULTS))
            s.add_item_totals(row, row.get(doc.ITEMS), s.ITEM_TOTALS_IGST)

            invoices[row[doc.DOC_NUMBER]] = row

    return output


def to_gov(rows, company_gstin=""):
    def write(row):
        out = s.round_money(s.pick_back(row, KEYS), MONEY)

        s.convert(out, raw.DOC_DATE, s.date_to_gov)
        s.convert(out, raw.SHIPPING_BILL_DATE, s.date_to_gov)
        s.convert(out, raw.ITEMS, lambda items: s.flat_items_to_gov(items, KEYS, ITEM_MONEY))

        return out

    return s.groups_from_rows(
        rows,
        group_key=lambda row: row[doc.DOC_TYPE],
        group_header=lambda row: {raw.EXPORT_TYPE: row[doc.DOC_TYPE]},
        rows_field=raw.INVOICES,
        write_row=write,
    )
