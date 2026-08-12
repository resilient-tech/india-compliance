"""Advances — tax paid on money received before the invoice, and its later adjustment (tables 11A, 11B).

Portal:    [{pos: "05", itms: [{rt: 5, ad_amt: 100, iamt: 5}]}]
Canonical: {"Advances Received": {"05-Uttarakhand - 5.0": [{place_of_supply: "05-Uttarakhand",
                                                            total_taxable_value: 100, tax_rate: 5}]}}

One canonical row per rate, so reading splits the portal's item list out into rows and writing
pulls the amounts back down into items. Adjustments are the same shape with the sign flipped --
they cancel a liability already declared.
"""

from frappe.utils import flt

from india_compliance.gst_returns.fields.gstr1 import DocField as doc
from india_compliance.gst_returns.fields.gstr1 import ItemField as item
from india_compliance.gst_returns.fields.gstr1 import RawField as raw
from india_compliance.gst_returns.fields.gstr1 import SubCategory

from . import _shared as s

RECEIVED = 1
ADJUSTED = -1

KEYS = {
    raw.FLAG: doc.FLAG,
    raw.POS: doc.POS,
    raw.DIFF_PERCENTAGE: doc.DIFF_PERCENTAGE,
    raw.ITEMS: doc.ITEMS,
    raw.TAX_RATE: item.TAX_RATE,
    raw.ADVANCE_AMOUNT: doc.TAXABLE_VALUE,
    raw.IGST: doc.IGST,
    raw.CGST: doc.CGST,
    raw.SGST: doc.SGST,
    raw.CESS: doc.CESS,
    raw.ERROR_CD: doc.ERROR_CD,
    raw.ERROR_MSG: doc.ERROR_MSG,
}

# amounts live on the row itself here, because each item becomes its own row
AMOUNTS = (doc.IGST, doc.CESS, doc.CGST, doc.SGST, doc.TAXABLE_VALUE)
ITEM_DEFAULTS = dict.fromkeys(AMOUNTS, 0)

# amounts the portal expects inside the item, in its own order
GOV_ITEM_FIELDS = (
    raw.IGST,
    raw.CESS,
    raw.CGST,
    raw.SGST,
    raw.ADVANCE_AMOUNT,
    raw.TAX_RATE,
)

MONEY = (
    raw.DIFF_PERCENTAGE,
    raw.ADVANCE_AMOUNT,
    raw.IGST,
    raw.CGST,
    raw.SGST,
    raw.CESS,
)


def group_key(row):
    """Identity used to match books against the portal. Discarded before the data is stored."""
    return " - ".join((row.get(doc.POS) or "", str(flt(row.get(item.TAX_RATE, "")))))


def to_canonical(gov_data, multiplier=RECEIVED):
    output = {}

    for entry in gov_data:
        row = s.drop_flag(s.pick(entry, KEYS))
        s.convert(row, doc.POS, s.pos_from_gov)  # 05 -> 05-Uttarakhand

        lines = s.flat_items_from_gov(row.pop(doc.ITEMS, []), KEYS, ITEM_DEFAULTS)

        for line in lines:
            s.flip_signs(line, multiplier, AMOUNTS)
            output[group_key({**row, **line})] = [{**row, **line}]  # keyed "05-Uttarakhand - 5.0"

    return output


def to_gov(rows, company_gstin="", multiplier=RECEIVED):
    by_pos = {}

    for row in rows:
        row = s.flip_signs(dict(row), multiplier, AMOUNTS)  # copy, the stored row keeps its sign

        out = s.drop_zero_diff(s.round_money(s.pick_back(row, KEYS), MONEY))
        s.convert(out, raw.POS, s.pos_to_gov)  # 05-Uttarakhand -> 05
        out[raw.SUPPLY_TYPE] = s.supply_type(out[raw.POS], company_gstin)  # seller 24, buyer 05 -> INTER

        # move this row's amounts into an item, leaving the state header behind
        line = {field: out.pop(field) for field in GOV_ITEM_FIELDS}

        by_pos.setdefault(row[doc.POS], out).setdefault(raw.ITEMS, []).append(line)

    return list(by_pos.values())


def received_to_canonical(gov_data):
    return {SubCategory.AT.value: to_canonical(gov_data, RECEIVED)}


def received_to_gov(rows, company_gstin=""):
    return to_gov(rows, company_gstin, RECEIVED)


def adjusted_to_canonical(gov_data):
    return {SubCategory.TXP.value: to_canonical(gov_data, ADJUSTED)}


def adjusted_to_gov(rows, company_gstin=""):
    return to_gov(rows, company_gstin, ADJUSTED)
