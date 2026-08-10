"""Credit and debit notes against unregistered buyers and exports (table 9B).

Portal:    [{ntty: "C", nt_num: "533515", typ: "B2CL", itms: [{num: 1, itm_det: {txval: 5225.28}}]}]
Canonical: {"Credit/Debit Notes (Unregistered)": {"533515": {transaction_type: "Credit Note",
                                                             items: [{taxable_value: -5225.28}],
                                                             total_taxable_value: -5225.28}}}

Same sign rule as registered notes: stored negative, filed unsigned.
"""

from india_compliance.gst_returns.fields.gstr1 import DocField as doc
from india_compliance.gst_returns.fields.gstr1 import ItemField as item
from india_compliance.gst_returns.fields.gstr1 import RawField as raw
from india_compliance.gst_returns.fields.gstr1 import SubCategory

from . import _shared as s
from .cdnr import NOTE_CODES, NOTE_TYPES, sign  # same portal field, same labels

SUBCATEGORY = SubCategory.CDNUR.value

KEYS = {
    raw.FLAG: doc.FLAG,
    raw.TYPE: doc.DOC_TYPE,
    raw.NOTE_TYPE: doc.TRANSACTION_TYPE,
    raw.NOTE_NUMBER: doc.DOC_NUMBER,
    raw.NOTE_DATE: doc.DOC_DATE,
    raw.DOC_VALUE: doc.DOC_VALUE,
    raw.POS: doc.POS,
    raw.DIFF_PERCENTAGE: doc.DIFF_PERCENTAGE,
    raw.ITEMS: doc.ITEMS,
    raw.TAX_RATE: item.TAX_RATE,
    raw.TAXABLE_VALUE: item.TAXABLE_VALUE,
    raw.IGST: item.IGST,
    raw.CESS: item.CESS,
    raw.ERROR_CD: doc.ERROR_CD,
    raw.ERROR_MSG: doc.ERROR_MSG,
}

# exports have no place of supply to report
EXPORT_TYPES = ("EXPWP", "EXPWOP")

ITEM_DEFAULTS = dict.fromkeys(s.ITEM_TOTALS_IGST, 0)

MONEY = (raw.DOC_VALUE, raw.DIFF_PERCENTAGE)
ITEM_MONEY = (raw.TAXABLE_VALUE, raw.IGST, raw.CESS)


def to_canonical(gov_data):
    output = {}

    for note in gov_data:
        multiplier = sign(note[raw.NOTE_TYPE])
        row = s.drop_flag(s.pick(note, KEYS))

        s.remap(row, doc.TRANSACTION_TYPE, NOTE_TYPES)  # C -> Credit Note
        s.convert(row, doc.DOC_DATE, s.date_from_gov)  # 23-09-2016 -> 2016-09-23
        s.convert(row, doc.POS, s.pos_from_gov)  # 03 -> 03-Punjab
        s.flip_signs(row, multiplier, (doc.DOC_VALUE,))  # credit note 123123 -> -123123

        row[doc.ITEMS] = [
            s.flip_signs(line, multiplier, ITEM_DEFAULTS)
            for line in s.wrapped_items_from_gov(note.get(raw.ITEMS), KEYS, ITEM_DEFAULTS)
        ]
        s.add_item_totals(row, row[doc.ITEMS], s.ITEM_TOTALS_IGST)

        output[row[doc.DOC_NUMBER]] = row

    return {SUBCATEGORY: output}


def to_gov(rows, company_gstin=""):
    def write(row):
        out = s.abs_amounts(s.round_money(s.pick_back(row, KEYS), MONEY), (raw.DOC_VALUE,))

        s.remap(out, raw.NOTE_TYPE, NOTE_CODES)  # Credit Note -> C
        s.convert(out, raw.NOTE_DATE, s.date_to_gov)  # 2016-09-23 -> 23-09-2016
        s.convert(out, raw.POS, s.pos_to_gov)  # 03-Punjab -> 03

        if row.get(doc.DOC_TYPE) in EXPORT_TYPES:
            out.pop(raw.POS, None)

        items = [s.abs_amounts(line, ITEM_DEFAULTS) for line in row[doc.ITEMS]]
        out[raw.ITEMS] = s.wrapped_items_to_gov(items, KEYS, ITEM_MONEY)

        return s.drop_zero_diff(out)

    return [write(row) for row in rows]
