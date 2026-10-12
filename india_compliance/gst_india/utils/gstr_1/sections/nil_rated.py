"""Nil rated, exempted and non-GST supplies, by who bought and from where (table 8)."""

from india_compliance.gst_returns.fields.gstr1 import DocField as doc
from india_compliance.gst_returns.fields.gstr1 import NilRatedCategory, SubCategory
from india_compliance.gst_returns.fields.gstr1 import RawField as raw

from . import _shared as s

SUBCATEGORY = SubCategory.NIL_EXEMPT.value

KEYS = {
    raw.SUPPLY_TYPE: doc.DOC_TYPE,
    raw.EXEMPTED_AMOUNT: doc.EXEMPTED_AMOUNT,
    raw.NIL_RATED_AMOUNT: doc.NIL_RATED_AMOUNT,
    raw.NON_GST_AMOUNT: doc.NON_GST_AMOUNT,
}

# sply_ty -> supply type
SUPPLY_TYPES = {
    "INTRB2B": NilRatedCategory.INTER_B2B.value,
    "INTRB2C": NilRatedCategory.INTER_B2C.value,
    "INTRAB2B": NilRatedCategory.INTRA_B2B.value,
    "INTRAB2C": NilRatedCategory.INTRA_B2C.value,
}
SUPPLY_CODES = s.flip(SUPPLY_TYPES)

# the three amounts behind the taxable value
AMOUNTS = (doc.EXEMPTED_AMOUNT, doc.NIL_RATED_AMOUNT, doc.NON_GST_AMOUNT)

MONEY = (raw.EXEMPTED_AMOUNT, raw.NIL_RATED_AMOUNT, raw.NON_GST_AMOUNT)


def to_canonical(gov_data):
    output = {}

    header = {
        doc.ERROR_CD: gov_data.get(raw.ERROR_CD),
        doc.ERROR_MSG: gov_data.get(raw.ERROR_MSG),
    }

    for entry in gov_data[raw.INVOICES]:
        row = s.with_defaults(s.pick(entry, KEYS), header)
        s.remap(row, doc.DOC_TYPE, SUPPLY_TYPES)  # INTRB2B -> Inter-State supplies to registered persons

        # nothing in the line, no supply
        if all(not row.get(field) for field in AMOUNTS):
            continue

        row[doc.TAXABLE_VALUE] = s.sum_money(row, AMOUNTS)

        output.setdefault(row.get(doc.DOC_TYPE), []).append(row)

    return {SUBCATEGORY: output}


def to_gov(rows, company_gstin=""):
    def write(row):
        out = s.round_money(s.pick_back(row, KEYS), MONEY)
        s.remap(out, raw.SUPPLY_TYPE, SUPPLY_CODES)  # Inter-State supplies to registered persons -> INTRB2B

        return out

    return {raw.INVOICES: [write(row) for row in rows]}
