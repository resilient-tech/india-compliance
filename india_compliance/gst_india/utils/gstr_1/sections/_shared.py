"""Steps every category shares.

Reading keeps blanks and rounds nothing, so the payload can be rebuilt. Writing rounds money;
blanks go at the JSON boundary.
"""

from datetime import datetime

import frappe
from frappe import _
from frappe.utils import flt

from india_compliance.gst_india.constants import (
    SERVICE_HSN_PREFIX,
    STATE_NUMBERS,
    UOM_MAP,
)
from india_compliance.gst_india.utils import get_party_for_gstin
from india_compliance.gst_returns.fields.gstr1 import DocField as doc
from india_compliance.gst_returns.fields.gstr1 import ItemField as item
from india_compliance.gst_returns.fields.gstr1 import RawField as raw

# generic steps live with the pure package; re-exported so sections keep one import
from india_compliance.gst_returns.steps import (
    add_item_totals,
    convert,
    flip,
    groups_from_rows,
    invert,
    is_blank,
    pick,
    pick_back,
    remap,
    rows_from_groups,
    strip_empty,
    with_defaults,
)

__all__ = [
    "add_item_totals",
    "convert",
    "flip",
    "groups_from_rows",
    "invert",
    "is_blank",
    "pick",
    "pick_back",
    "remap",
    "rows_from_groups",
    "strip_empty",
    "with_defaults",
]

# state number -> state name
STATE_NAMES = {number: name for name, number in STATE_NUMBERS.items()}

# item amount -> its invoice total
ITEM_TOTALS = {
    item.TAXABLE_VALUE: doc.TAXABLE_VALUE,
    item.IGST: doc.IGST,
    item.CGST: doc.CGST,
    item.SGST: doc.SGST,
    item.CESS: doc.CESS,
}

# inter-state: no central or state tax
ITEM_TOTALS_IGST = {
    item.TAXABLE_VALUE: doc.TAXABLE_VALUE,
    item.IGST: doc.IGST,
    item.CESS: doc.CESS,
}


# ── keys ──────────────────────────────────────────────────────────────────────


def drop_flag(row):
    """Portal row marker means nothing once the row is ours."""
    row.pop(doc.FLAG, None)
    return row


def drop_zero_diff(row):
    """The portal rejects a zero rate difference."""
    if not row.get(raw.DIFF_PERCENTAGE):
        row.pop(raw.DIFF_PERCENTAGE, None)

    return row


# ── values ────────────────────────────────────────────────────────────────────


def pos_from_gov(number):
    """ "05" -> "05-Uttarakhand", what we store everywhere."""
    name = STATE_NAMES.get(number)

    return f"{number}-{name}" if name else number


def pos_to_gov(pos):
    """ "05-Uttarakhand" -> "05"."""
    return pos.split("-")[0]


def date_from_gov(value):
    """Portal writes dates day-first."""
    return datetime.strptime(value, "%d-%m-%Y").strftime("%Y-%m-%d")


def date_to_gov(value):
    return datetime.strptime(value, "%Y-%m-%d").strftime("%d-%m-%Y")


def uom_from_gov(uom):
    """ "BOX" -> "BOX-BOX". Unknown units report as other."""
    return _uom(uom)


def uom_to_gov(uom, hsn_code=None):
    """ "BOX-BOX" -> "BOX". Services have no unit."""
    if "-" in uom.upper() and hsn_code and hsn_code.startswith(SERVICE_HSN_PREFIX):
        return "NA"

    return _uom(uom)


def _uom(uom):
    uom = uom.upper()

    if "-" in uom:
        return uom.split("-")[0]

    if uom in UOM_MAP:
        return f"{uom}-{UOM_MAP[uom]}"

    return f"OTH-{UOM_MAP.get('OTH')}"


def customer_name(gstin, cache):
    """Name behind a GSTIN, looked up once per download. Unknown until the Customer exists."""
    if gstin not in cache:
        cache[gstin] = get_party_for_gstin(gstin, "Customer") or "Unknown"

    return cache[gstin]


# ── amounts ───────────────────────────────────────────────────────────────────


def money(value):
    """Two decimals, as the portal expects."""
    return flt(value, 2)


def round_money(row, fields):
    """Round the named amounts in place."""
    for field in fields:
        convert(row, field, money)

    return row


def sum_money(row, fields):
    """Rounded total of the named amounts on one row. Blank counts as nothing."""
    return flt(sum(row.get(field) or 0 for field in fields), 2)


def sum_column(rows, field):
    """Rounded total of one amount over many rows. Blank counts as nothing."""
    return flt(sum(row.get(field) or 0 for row in rows), 2)


def split(total, weights):
    """
    Share `total` out over `weights` so the pieces add back to it exactly. Signs are irrelevant.
        split(10.00, [3.333, 3.333, 3.334])  ->  [3.33, 3.34, 3.33]   adds to 10.00
    """
    pieces = []
    last = max((index for index, weight in enumerate(weights) if weight), default=len(weights) - 1)
    seen = done = 0.0

    for index, weight in enumerate(weights):
        if index > last:
            pieces.append(0.0)
            continue

        seen += weight
        upto = total if index == last else money(seen)
        pieces.append(money(upto - done))
        done = upto

    return pieces


def flip_signs(row, multiplier, fields):
    """Negate the named amounts. Notes and adjustments reduce liability."""
    if multiplier == 1:
        return row

    for field in fields:
        if not is_blank(row.get(field)):
            row[field] = row[field] * multiplier

    return row


def abs_amounts(row, fields):
    """The portal wants amounts unsigned."""
    for field in fields:
        convert(row, field, abs)

    return row


def supply_type(pos, company_gstin):
    """Same state as the seller means intra-state."""
    if not company_gstin:
        frappe.throw(_("Company GSTIN is needed to tell an intra-state supply from an inter-state one"))

    return "INTRA" if pos == company_gstin[:2] else "INTER"


# ── items ─────────────────────────────────────────────────────────────────────


def wrapped_items_from_gov(items, keys, defaults):
    """Portal nests each item under "itm_det". Missing amounts read as zero."""
    return [{**defaults, **pick(line.get(raw.ITEM_DETAILS, {}), keys)} for line in items or []]


def wrapped_items_to_gov(items, keys, money_fields):
    return [
        {
            raw.INDEX: index + 1,
            raw.ITEM_DETAILS: round_money(pick_back(line, keys), money_fields),
        }
        for index, line in enumerate(items)
    ]


def flat_items_from_gov(items, keys, defaults):
    """Some categories list item amounts with no wrapper."""
    return [{**defaults, **pick(line, keys)} for line in items or []]


def flat_items_to_gov(items, keys, money_fields):
    return [round_money(pick_back(line, keys), money_fields) for line in items]
