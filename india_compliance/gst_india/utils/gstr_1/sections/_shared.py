"""Named steps shared by every GSTR-1 category.

Replaces the old `GovDataMapper.format_data`: each step has a name and is called on a visible
line, instead of being dispatched from a formatter dict behind a `for_gov` flag.

Two rules the package relies on:
    reading   keep blanks, round nothing -- canonical must be able to rebuild the portal payload
    writing   round money, then drop blanks at the JSON boundary, which is where the portal cares
"""

from datetime import datetime

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

# item amount -> the invoice total it adds up to
ITEM_TOTALS = {
    item.TAXABLE_VALUE: doc.TAXABLE_VALUE,
    item.IGST: doc.IGST,
    item.CGST: doc.CGST,
    item.SGST: doc.SGST,
    item.CESS: doc.CESS,
}

# inter-state categories carry no central or state tax
ITEM_TOTALS_IGST = {
    item.TAXABLE_VALUE: doc.TAXABLE_VALUE,
    item.IGST: doc.IGST,
    item.CESS: doc.CESS,
}


# ── keys ──────────────────────────────────────────────────────────────────────


def pick(src, keys):
    """Portal row -> canonical row, in table order. Unlisted keys dropped, blanks kept."""
    return {new: src[old] for old, new in keys.items() if old in src}


def pick_back(src, keys):
    """Canonical row -> portal row. Same table, read the other way."""
    return {old: src[new] for old, new in keys.items() if new in src}


def flip(mapping):
    """Reverse a lookup table."""
    return {value: key for key, value in mapping.items()}


def invert(keys):
    """Reverse a key table, refusing to lose a key."""
    flipped = flip(keys)
    if len(flipped) != len(keys):
        raise ValueError("key table is not reversible")

    return flipped


def with_defaults(row, defaults):
    """Put fixed fields in front of a row. Blank defaults are dropped -- they are not portal data."""
    return {**{k: v for k, v in defaults.items() if v or v == 0}, **row}


def convert(row, field, using):
    """Rewrite one field through the given function.

    Blanks pass straight through -- there is nothing to convert, and the boundary drops them.
    Zero does not: it is a real amount and still gets rounded.
    """
    if field in row and not is_blank(row[field]):
        row[field] = using(row[field])

    return row


def remap(row, field, table):
    """Swap one coded value using the given table, if the row has it."""
    if field in row:
        row[field] = table.get(row[field], row[field])

    return row


def drop_flag(row):
    """The portal's row marker means nothing once the row is ours."""
    row.pop(doc.FLAG, None)
    return row


def drop_zero_diff(row):
    """The portal rejects a zero rate difference."""
    if not row.get(raw.DIFF_PERCENTAGE):
        row.pop(raw.DIFF_PERCENTAGE, None)

    return row


# ── values ────────────────────────────────────────────────────────────────────


def pos_from_gov(number):
    """Portal sends the state number only; the app stores "05-Uttarakhand" everywhere."""
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
    """Name behind a GSTIN, looked up once per download.

    The one canonical field not derived from the payload, so a row mapped before its Customer
    exists keeps saying "Unknown". Moves to render time with the Excel rewrite.
    """
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
    """Rounded total of the named amounts. A blank counts as nothing."""
    return flt(sum(row.get(field) or 0 for field in fields), 2)


def add_item_totals(row, items, totals):
    """Add item amounts into the invoice totals. Accumulates, so call once per invoice."""
    for line in items or []:
        for field, total in totals.items():
            if not is_blank(line.get(field)):
                row[total] = (row.get(total) or 0) + line[field]

    return row


def flip_signs(row, multiplier, fields):
    """Negate the named amounts -- credit notes and adjustments reduce liability."""
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
        raise ValueError("company_gstin is needed to tell intra-state from inter-state")

    return "INTRA" if pos == company_gstin[:2] else "INTER"


# ── items ─────────────────────────────────────────────────────────────────────


def wrapped_items_from_gov(items, keys, defaults):
    """Portal nests each item under "itm_det". Amounts the portal omits read as zero."""
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
    """Some categories list item amounts directly, with no wrapper."""
    return [{**defaults, **pick(line, keys)} for line in items or []]


def flat_items_to_gov(items, keys, money_fields):
    return [round_money(pick_back(line, keys), money_fields) for line in items]


# ── shapes ────────────────────────────────────────────────────────────────────


def groups_from_rows(rows, group_key, group_header, rows_field, write_row):
    """Our flat rows -> the portal's grouped shape, one group per key.

        [{customer_gstin: "24AA...", document_number: "S1"}, ...]
     -> [{ctin: "24AA...", inv: [{inum: "S1"}, ...]}]

    The first row of a key writes the group's header; later rows only add to its list.
    """
    groups = {}

    for row in rows:
        group = groups.setdefault(group_key(row), {**group_header(row), rows_field: []})
        group[rows_field].append(write_row(row))

    return list(groups.values())


def rows_from_groups(groups, rows_field, group_header, read_row):
    """The portal's grouped shape -> our flat rows, with the group's own fields on each.

       [{ctin: "24AA...", inv: [{inum: "S1"}, ...]}]
    -> [{customer_gstin: "24AA...", document_number: "S1"}, ...]
    """
    for group in groups:
        header = group_header(group)

        for row in group.get(rows_field) or []:
            yield read_row(row, header)


def strip_empty(value):
    """Drop the blanks the portal rejects. Zero and False stay -- they are real amounts."""
    if isinstance(value, dict):
        return {k: strip_empty(v) for k, v in value.items() if not is_blank(v)}

    if isinstance(value, list):
        return [strip_empty(v) for v in value]

    return value


def is_blank(value):
    return value is None or value == "" or value == {} or value == []
