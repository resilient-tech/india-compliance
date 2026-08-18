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


def pick(src, keys):
    """Portal row -> our row, table order. Unlisted keys go, blanks stay."""
    return {new: src[old] for old, new in keys.items() if old in src}


def pick_back(src, keys):
    """Our row -> portal row. Same table, other way."""
    return {old: src[new] for old, new in keys.items() if new in src}


def flip(mapping):
    """Reverse a lookup table."""
    return {value: key for key, value in mapping.items()}


def invert(keys):
    """Reverse a key table. Refuses to lose a key."""
    flipped = flip(keys)
    if len(flipped) != len(keys):
        raise ValueError("key table is not reversible")

    return flipped


def with_defaults(row, defaults):
    """Fixed fields in front of a row. Blank ones are dropped."""
    return {**{k: v for k, v in defaults.items() if v or v == 0}, **row}


def convert(row, field, using):
    """Rewrite one field. Blanks pass through, zero does not -- it is a real amount."""
    if field in row and not is_blank(row[field]):
        row[field] = using(row[field])

    return row


def remap(row, field, table):
    """Swap one coded value using the given table, if the row has it."""
    if field in row:
        row[field] = table.get(row[field], row[field])

    return row


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


def add_item_totals(row, items, totals):
    """Item amounts into the invoice totals. Adds up, so call once per invoice."""
    for line in items or []:
        for field, total in totals.items():
            if not is_blank(line.get(field)):
                row[total] = (row.get(total) or 0) + line[field]

    return row


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


# ── shapes ────────────────────────────────────────────────────────────────────


def groups_from_rows(rows, group_key, group_header, rows_field, write_row):
    """Our rows -> the portal's groups. First row of a key writes the header."""
    groups = {}

    for row in rows:
        group = groups.setdefault(group_key(row), {**group_header(row), rows_field: []})
        group[rows_field].append(write_row(row))

    return list(groups.values())


def rows_from_groups(groups, rows_field, group_header, read_row):
    """The portal's groups -> our rows, group fields copied onto each."""
    for group in groups:
        header = group_header(group)

        for row in group.get(rows_field) or []:
            yield read_row(row, header)


def strip_empty(value):
    """Drop the blanks the portal rejects. Zero and False stay."""
    if isinstance(value, dict):
        return {k: strip_empty(v) for k, v in value.items() if not is_blank(v)}

    if isinstance(value, list):
        return [strip_empty(v) for v in value]

    return value


def is_blank(value):
    return value is None or value == "" or value == {} or value == []
