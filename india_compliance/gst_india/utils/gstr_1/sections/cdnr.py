"""Credit and debit notes to registered buyers (table 9B).

Credit note reduces what is owed, so we store it negative. Portal wants unsigned plus a note type.
"""

from india_compliance.gst_returns.fields.gstr1 import CreditDebitNoteType, SubCategory
from india_compliance.gst_returns.fields.gstr1 import DocField as doc
from india_compliance.gst_returns.fields.gstr1 import ItemField as item
from india_compliance.gst_returns.fields.gstr1 import RawField as raw

from . import _shared as s
from .b2b import INVOICE_CODES, INVOICE_TYPES  # same portal field, same labels

SUBCATEGORY = SubCategory.CDNR.value

LEGACY_INVOICE_CODES = {**INVOICE_CODES, SubCategory.DE.value: "DE"}

KEYS = {
    raw.FLAG: doc.FLAG,
    raw.NOTE_TYPE: doc.TRANSACTION_TYPE,
    raw.NOTE_NUMBER: doc.DOC_NUMBER,
    raw.NOTE_DATE: doc.DOC_DATE,
    raw.POS: doc.POS,
    raw.REVERSE_CHARGE: doc.REVERSE_CHARGE,
    raw.INVOICE_TYPE: doc.DOC_TYPE,
    raw.DOC_VALUE: doc.DOC_VALUE,
    raw.DIFF_PERCENTAGE: doc.DIFF_PERCENTAGE,
    raw.ITEMS: doc.ITEMS,
    raw.TAX_RATE: item.TAX_RATE,
    raw.TAXABLE_VALUE: item.TAXABLE_VALUE,
    raw.IGST: item.IGST,
    raw.SGST: item.SGST,
    raw.CGST: item.CGST,
    raw.CESS: item.CESS,
}

# ntty -> note type
NOTE_TYPES = {
    "C": CreditDebitNoteType.C.value,
    "D": CreditDebitNoteType.D.value,
}
NOTE_CODES = s.flip(NOTE_TYPES)

SUBCATEGORIES = (SUBCATEGORY,)

ITEM_DEFAULTS = dict.fromkeys(s.ITEM_TOTALS, 0)
ITEM_AMOUNTS = tuple(ITEM_DEFAULTS)

MONEY = (raw.DOC_VALUE, raw.DIFF_PERCENTAGE)
ITEM_MONEY = (raw.TAXABLE_VALUE, raw.IGST, raw.SGST, raw.CGST, raw.CESS)

CREDIT_NOTE = "C"


def sign(note_type):
    """Credit notes stored negative, debit notes positive."""
    return -1 if note_type == CREDIT_NOTE else 1


def to_canonical(gov_data):
    names = {}
    output = {}

    def buyer(group):
        gstin = group.get(raw.CUST_GSTIN)
        return {
            doc.CUST_GSTIN: gstin,
            doc.CUST_NAME: s.customer_name(gstin, names),
            doc.ERROR_CD: group.get(raw.ERROR_CD),
            doc.ERROR_MSG: group.get(raw.ERROR_MSG),
        }

    def read(note, header):
        multiplier = sign(note[raw.NOTE_TYPE])
        row = s.drop_flag(s.with_defaults(s.pick(note, KEYS), header))

        s.remap(row, doc.TRANSACTION_TYPE, NOTE_TYPES)  # C -> Credit Note
        s.remap(row, doc.DOC_TYPE, INVOICE_TYPES)  # DE -> Deemed Exp
        s.convert(row, doc.DOC_DATE, s.date_from_gov)
        s.convert(row, doc.POS, s.pos_from_gov)
        s.flip_signs(row, multiplier, (doc.DOC_VALUE,))

        row[doc.ITEMS] = [
            s.flip_signs(line, multiplier, ITEM_AMOUNTS)
            for line in s.wrapped_items_from_gov(note.get(raw.ITEMS), KEYS, ITEM_DEFAULTS)
        ]
        s.add_item_totals(row, row[doc.ITEMS], s.ITEM_TOTALS)

        return row

    for row in s.rows_from_groups(gov_data, raw.NOTE_DETAILS, buyer, read):
        output[row[doc.DOC_NUMBER]] = row

    return {SUBCATEGORY: output}


def from_books(grouped_rows):
    """Books rows -> one row per invoice, for the subcategories this category reports."""
    return s.invoice_rows_from_books(grouped_rows, SUBCATEGORIES)


def to_gov(rows, company_gstin=""):
    def write(row):
        out = s.round_money(s.abs_amounts(s.pick_back(row, KEYS), (raw.DOC_VALUE,)), MONEY)

        s.remap(out, raw.NOTE_TYPE, NOTE_CODES)  # Credit Note -> C
        s.remap(out, raw.INVOICE_TYPE, LEGACY_INVOICE_CODES)  # Deemed Exp -> DE
        s.convert(out, raw.NOTE_DATE, s.date_to_gov)
        s.convert(out, raw.POS, s.pos_to_gov)

        items = [s.abs_amounts(dict(line), ITEM_AMOUNTS) for line in row[doc.ITEMS]]
        out[raw.ITEMS] = s.wrapped_items_to_gov(items, KEYS, ITEM_MONEY)

        return s.drop_zero_diff(out)

    return s.groups_from_rows(
        rows,
        group_key=lambda row: row[doc.CUST_GSTIN],
        group_header=lambda row: {raw.CUST_GSTIN: row[doc.CUST_GSTIN]},
        rows_field=raw.NOTE_DETAILS,
        write_row=write,
    )
