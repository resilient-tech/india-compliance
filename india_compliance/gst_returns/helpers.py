import math
from datetime import date, datetime


def round_to(value, precision=2):
    """Round like frappe does. 2.675 -> 2.68."""
    if value is None:
        return 0.0

    factor = 10**precision
    scaled = round(float(value) * factor, 8)
    floor = math.floor(scaled)
    scaled = floor + 1 if scaled - floor == 0.5 else round(scaled)
    return scaled / factor


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
