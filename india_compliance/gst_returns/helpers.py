import math
from datetime import date, datetime


def round2(value):
    """2 decimal places round. Not naive (2.675 -> 2.68)."""
    if value is None:
        return 0.0

    scaled = round(float(value) * 100, 8)
    floor = math.floor(scaled)
    scaled = floor + 1 if scaled - floor == 0.5 else round(scaled)
    return scaled / 100


def split(total, weights, round_fn=round2):
    """
    Share `total` out over `weights` so the pieces add back to it exactly. Signs are irrelevant.
        split(10.00, [3.333, 3.333, 3.334])  ->  [3.33, 3.34, 3.33]   adds to 10.00
    """
    pieces = []
    last = max((index for index, weight in enumerate(weights) if weight), default=-1)
    seen = done = 0.0

    for index, weight in enumerate(weights):
        if index > last:
            pieces.append(0.0)
            continue

        seen += weight
        upto = total if index == last else round_fn(seen)
        pieces.append(round_fn(upto - done))
        done = upto

    return pieces


def parse_date(value, fmt="%Y-%m-%d"):
    """str -> date"""
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(value, fmt).date()


def format_date(value, fmt="%Y-%m-%d"):
    """date -> str"""
    if value is None:
        return None
    return value.strftime(fmt)
