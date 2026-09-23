"""Mapping steps every return shares. Pure, no frappe.

Two ways to read a portal row, both here so the difference stays visible:
`pick` keeps only the keys the portal sent (GSTR-1 -- canonical must rebuild the payload);
`take` lands every listed field, absent ones as None (2A/2B -- a re-download must be able
to clear a stale value on the stored row).
"""


# ── keys ──────────────────────────────────────────────────────────────────────


def pick(src, keys):
    """Portal row -> our row, table order. Unlisted keys go, blanks stay."""
    return {new: src[old] for old, new in keys.items() if old in src}


def pick_back(src, keys):
    """Our row -> portal row. Same table, other way."""
    return {old: src[new] for old, new in keys.items() if new in src}


def take(src, keys):
    """Portal row -> our row, every listed field. Absent reads as None."""
    return {new: src.get(old) for old, new in keys.items()}


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


def decode(row, field, table):
    """Swap a coded value using the given table. A code the table lacks reads as None."""
    row[field] = table.get(row.get(field))

    return row


# ── amounts ───────────────────────────────────────────────────────────────────


def add_item_totals(row, items, totals):
    """Item amounts into the invoice totals. Adds up, so call once per invoice."""
    for line in items or []:
        for field, total in totals.items():
            if not is_blank(line.get(field)):
                row[total] = (row.get(total) or 0) + line[field]

    return row


def set_item_totals(row, items, fields):
    """Item amounts become the invoice totals, replacing whatever the row had."""
    for field in fields:
        row[field] = sum([line.get(field) for line in items if line.get(field)])

    return row


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
