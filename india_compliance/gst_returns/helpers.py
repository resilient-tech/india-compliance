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
