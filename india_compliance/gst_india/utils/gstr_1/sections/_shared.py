"""Steps every category shares.

Reading keeps blanks and rounds nothing, so the payload can be rebuilt. Writing rounds money;
blanks go at the JSON boundary.
"""

from datetime import datetime
from itertools import chain

import frappe
from frappe import _
from frappe.utils import flt

from india_compliance.gst_india.constants import (
    SERVICE_HSN_PREFIX,
    STATE_NUMBERS,
    UOM_MAP,
)
from india_compliance.gst_india.utils import get_party_for_gstin
from india_compliance.gst_returns.fields.gstr1 import CreditDebitNoteType
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

# the same five amounts as the books query names them
BOOKS_COLUMNS = {
    doc.TAXABLE_VALUE: "taxable_value",
    doc.IGST: "igst_amount",
    doc.CGST: "cgst_amount",
    doc.SGST: "sgst_amount",
    doc.CESS: "total_cess_amount",
}

# and as an item names them
ITEM_COLUMNS = {line: BOOKS_COLUMNS[total] for line, total in ITEM_TOTALS.items()}

# a books row that is not a note is an invoice; the portal has codes only for the notes
INVOICE = "Invoice"

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


# ── books ─────────────────────────────────────────────────────────────────────


def transaction_type(row):
    """What kind of document a books row came from."""
    if row.is_debit_note:
        return CreditDebitNoteType.D.value

    if row.is_return:
        return CreditDebitNoteType.C.value

    return INVOICE


def zero_totals():
    """A fresh set of invoice totals, all at nothing."""
    return dict.fromkeys(BOOKS_COLUMNS, 0)


def invoice_rows_from_books(grouped_rows, subcategories):
    """One canonical row per invoice, for the subcategories the caller reports.

    B2B, B2CL, exports and both kinds of credit note all report invoice by invoice, so they share
    this builder and each passes the subcategories it owns. The row is a superset -- shipping
    fields, buyer GSTIN and reverse charge are always written, and each category's key table drops
    whatever it does not report.

        {("B2B Regular", "S008400"): {18.0: [item rows]}}
     -> {"B2B Regular": {"S008400": {document_number: "S008400", items: [{tax_rate: 18.0}]}}}
    """
    output = {}

    for (subcategory, invoice_no), rows_by_rate in grouped_rows.items():
        if subcategory not in subcategories:
            continue

        first = next(iter(chain(*rows_by_rate.values())))

        row = {
            doc.TRANSACTION_TYPE: transaction_type(first),
            doc.CUST_GSTIN: first.billing_address_gstin,
            doc.CUST_NAME: first.customer_name,
            doc.DOC_DATE: first.posting_date,
            doc.DOC_NUMBER: first.invoice_no,
            doc.DOC_VALUE: first.invoice_total,
            doc.POS: first.place_of_supply,
            doc.REVERSE_CHARGE: ("Y" if first.is_reverse_charge else "N"),
            doc.DOC_TYPE: first.invoice_type,
            **zero_totals(),
            doc.DIFF_PERCENTAGE: 0,
            doc.SHIPPING_PORT_CODE: first.shipping_port_code,
            doc.SHIPPING_BILL_NUMBER: first.shipping_bill_number,
            doc.SHIPPING_BILL_DATE: first.shipping_bill_date,
            "items": [],
        }

        # one item per tax rate, because that is how the portal wants a return reported
        for rate, rows in rows_by_rate.items():
            line = {field: sum_column(rows, column) for field, column in ITEM_COLUMNS.items()}
            line[item.TAX_RATE] = rate
            row["items"].append(line)

        # amounts arrive settled to two decimals, so the totals only have to add up
        for field, total in ITEM_TOTALS.items():
            row[total] = sum_column(row["items"], field)

        output.setdefault(subcategory, {})[invoice_no] = row

    return output


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
