"""Tax on money taken before the invoice, and its later adjustment (tables 11A, 11B).

One row per rate, so reading splits the portal's items into rows and writing puts them back.
Adjustments are the same shape, sign flipped.
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

# amounts sit on the row, since each item becomes a row
AMOUNTS = (doc.IGST, doc.CESS, doc.CGST, doc.SGST, doc.TAXABLE_VALUE)
ITEM_DEFAULTS = dict.fromkeys(AMOUNTS, 0)

# what the portal wants inside the item, its order
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
    """Row identity, books against portal. Not stored."""
    return " - ".join((row.get(doc.POS) or "", str(flt(row.get(item.TAX_RATE, "")))))


def to_canonical(gov_data, multiplier=RECEIVED):
    output = {}

    for entry in gov_data:
        row = s.drop_flag(s.pick(entry, KEYS))
        s.convert(row, doc.POS, s.pos_from_gov)

        lines = s.flat_items_from_gov(row.pop(doc.ITEMS, []), KEYS, ITEM_DEFAULTS)

        for line in lines:
            s.flip_signs(line, multiplier, AMOUNTS)
            output[group_key({**row, **line})] = [{**row, **line}]  # keyed "05-Uttarakhand - 5.0"

    return output


def to_gov(rows, company_gstin="", multiplier=RECEIVED):
    by_pos = {}

    for row in rows:
        row = s.flip_signs(dict(row), multiplier, AMOUNTS)  # copy, stored row keeps its sign

        out = s.drop_zero_diff(s.round_money(s.pick_back(row, KEYS), MONEY))
        s.convert(out, raw.POS, s.pos_to_gov)
        out[raw.SUPPLY_TYPE] = s.supply_type(out[raw.POS], company_gstin)

        # amounts go into an item, state header stays
        line = {field: out.pop(field) for field in GOV_ITEM_FIELDS}

        by_pos.setdefault(row[doc.POS], out).setdefault(raw.ITEMS, []).append(line)

    return list(by_pos.values())


def from_books(rows, multiplier=RECEIVED):
    """Books advance entries -> one row per state and rate.

        [{party: "X", taxable_value: 100, tax_amount: 18, place_of_supply: "05-Uttarakhand"}]
     -> {"05-Uttarakhand - 18.0": [{total_taxable_value: 100, tax_rate: 18}]}

    The rate is worked back out of the tax, because an advance is taken before any line exists.
    """
    output = {}

    for entry in rows:
        rate = round((entry["tax_amount"] / entry["taxable_value"]) * 100)
        intra_state = entry["place_of_supply"][:2] == entry["company_gstin"][:2]

        row = {
            doc.CUST_NAME: entry["party"],
            doc.DOC_NUMBER: entry["name"],
            doc.DOC_DATE: entry["posting_date"],
            doc.POS: entry["place_of_supply"],
            doc.TAXABLE_VALUE: entry["taxable_value"] * multiplier,
            doc.TAX_RATE: rate,
            doc.CESS: entry["cess_amount"] * multiplier,
        }

        if entry.get("reference_name"):
            row["against_voucher"] = entry["reference_name"]

        # an advance carries no items, so the tax is split here rather than per line
        half = entry["tax_amount"] / 2 * multiplier
        row[doc.CGST] = half if intra_state else 0
        row[doc.SGST] = half if intra_state else 0
        row[doc.IGST] = 0 if intra_state else entry["tax_amount"] * multiplier

        output.setdefault(f"{entry['place_of_supply']} - {flt(rate)}", []).append(row)

    return output


def received_from_books(rows):
    return from_books(rows, RECEIVED)


def adjusted_from_books(rows):
    return from_books(rows, ADJUSTED)


def received_to_canonical(gov_data):
    return {SubCategory.AT.value: to_canonical(gov_data, RECEIVED)}


def received_to_gov(rows, company_gstin=""):
    return to_gov(rows, company_gstin, RECEIVED)


def adjusted_to_canonical(gov_data):
    return {SubCategory.TXP.value: to_canonical(gov_data, ADJUSTED)}


def adjusted_to_gov(rows, company_gstin=""):
    return to_gov(rows, company_gstin, ADJUSTED)
