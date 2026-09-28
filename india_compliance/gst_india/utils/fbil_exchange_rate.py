# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

"""
FBIL (Financial Benchmarks India Pvt. Ltd.) reference rates → Currency Exchange.

FBIL publishes INR reference rates for USD, EUR and GBP on Mumbai business days
(around 13:30 IST). When enabled in GST Settings, this module:

- syncs those rates into Currency Exchange on a schedule (see hooks.py), and
- applies the latest rate on or before the posting date as the conversion rate
  of foreign currency Sales Invoices of Indian companies whose default currency
  is INR.

The public (unauthenticated) FBIL endpoint publishes rates with a lag, so the
sync looks back a couple of weeks and the invoice hook falls back to the latest
available rate on or before the posting date.
"""

from __future__ import annotations

import re

import frappe
import requests
from frappe import _
from frappe.utils import add_days, cint, flt, formatdate, getdate, nowdate

FBIL_REF_RATES_URL = "https://www.fbil.org.in/wasdm/refrates/fetchfiltered"
FBIL_CURRENCIES = ("USD", "EUR", "GBP")
TO_CURRENCY = "INR"
RATE_PRECISION = 6
DEFAULT_SYNC_DAYS_BACK = 14
ON_DEMAND_LOOKBACK_DAYS = 21
REQUEST_TIMEOUT = 30

# e.g. "INR / 1 EUR" (JPY is published per 100 units and is intentionally skipped)
_SUB_PROD_PATTERN = re.compile(r"^INR\s*/\s*1\s+([A-Z]{3})$")


def is_fbil_exchange_rate_enabled() -> bool:
    return bool(frappe.get_cached_value("GST Settings", "GST Settings", "enable_fbil_exchange_rate"))


def fetch_fbil_reference_rates(
    from_date,
    to_date=None,
    currencies: tuple[str, ...] | list[str] | None = None,
) -> list[frappe._dict]:
    """
    Fetch FBIL reference rates published between from_date and to_date (inclusive).

    Returns a list of {date, currency, rate} sorted by date.
    """
    from_date = getdate(from_date)
    to_date = getdate(to_date) if to_date else from_date
    currencies = _normalize_currencies(currencies)

    try:
        response = requests.get(
            FBIL_REF_RATES_URL,
            params={
                "fromDate": str(from_date),
                "toDate": str(to_date),
                "authenticated": "false",
            },
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as e:
        frappe.log_error(title=_("FBIL Reference Rates Fetch Failed"), message=frappe.get_traceback())
        frappe.throw(_("Unable to fetch FBIL reference rates: {0}").format(e))

    if not isinstance(payload, list):
        frappe.throw(_("Unexpected response from FBIL reference rates API"))

    rows = []
    for item in payload:
        if not isinstance(item, dict):
            continue

        match = _SUB_PROD_PATTERN.match((item.get("subProdName") or "").strip())
        if not match or match.group(1) not in currencies:
            continue

        rate = flt(item.get("rate"))
        published_on = item.get("processRunDate") or item.get("displayTime")
        if rate <= 0 or not published_on:
            continue

        rows.append(frappe._dict(date=getdate(published_on), currency=match.group(1), rate=rate))

    rows.sort(key=lambda row: row.date)
    return rows


def upsert_currency_exchange(date, from_currency: str, exchange_rate: float) -> tuple[str, str]:
    """
    Create or update the Currency Exchange record for from_currency → INR on date.

    Returns (name, status) where status is one of "created", "updated" or "unchanged".
    """
    date = getdate(date)
    from_currency = from_currency.upper()
    exchange_rate = flt(exchange_rate, RATE_PRECISION)

    existing = frappe.db.get_value(
        "Currency Exchange",
        {"date": date, "from_currency": from_currency, "to_currency": TO_CURRENCY},
        ["name", "exchange_rate", "for_buying", "for_selling"],
        as_dict=True,
    )

    if existing:
        updates = {}
        if flt(existing.exchange_rate, RATE_PRECISION) != exchange_rate:
            updates["exchange_rate"] = exchange_rate
        if not cint(existing.for_buying):
            updates["for_buying"] = 1
        if not cint(existing.for_selling):
            updates["for_selling"] = 1

        if not updates:
            return existing.name, "unchanged"

        frappe.db.set_value("Currency Exchange", existing.name, updates)
        return existing.name, "updated"

    doc = frappe.get_doc(
        {
            "doctype": "Currency Exchange",
            "date": date,
            "from_currency": from_currency,
            "to_currency": TO_CURRENCY,
            "exchange_rate": exchange_rate,
            "for_buying": 1,
            "for_selling": 1,
        }
    ).insert(ignore_permissions=True)

    return doc.name, "created"


def sync_fbil_currency_exchange(
    currencies: tuple[str, ...] | list[str] | None = None,
    days_back: int = DEFAULT_SYNC_DAYS_BACK,
    from_date=None,
    to_date=None,
) -> frappe._dict:
    """
    Sync FBIL reference rates into Currency Exchange. Idempotent.

    Scheduled on weekday afternoons (site timezone); can also be run manually
    via `bench execute` with the dotted path of this function.
    """
    if not is_fbil_exchange_rate_enabled():
        return frappe._dict(skipped=True, created=0, updated=0, unchanged=0, rates=[])

    to_date = getdate(to_date or nowdate())
    from_date = getdate(from_date) if from_date else add_days(to_date, -cint(days_back))

    counts = {"created": 0, "updated": 0, "unchanged": 0}
    synced = []

    for row in fetch_fbil_reference_rates(from_date, to_date, currencies):
        name, status = upsert_currency_exchange(row.date, row.currency, row.rate)
        counts[status] += 1
        synced.append(
            frappe._dict(
                name=name,
                date=str(row.date),
                currency=row.currency,
                rate=flt(row.rate, RATE_PRECISION),
                status=status,
            )
        )

    return frappe._dict(
        skipped=False,
        from_date=str(from_date),
        to_date=str(to_date),
        rates=synced,
        **counts,
    )


def get_fbil_exchange_rate(from_currency: str, on_date=None, fetch_if_missing: bool = True) -> float | None:
    """
    Return the from_currency → INR selling rate from Currency Exchange for the
    latest date on or before on_date.

    If no record exists and fetch_if_missing is set, the recent FBIL history is
    fetched and stored before retrying.
    """
    from_currency = (from_currency or "").upper()
    if not from_currency:
        return None

    if from_currency == TO_CURRENCY:
        return 1.0

    on_date = getdate(on_date or nowdate())

    rate = frappe.db.get_value(
        "Currency Exchange",
        {
            "from_currency": from_currency,
            "to_currency": TO_CURRENCY,
            "date": ("<=", on_date),
            "for_selling": 1,
        },
        "exchange_rate",
        order_by="date desc",
    )
    if rate:
        return flt(rate, RATE_PRECISION)

    if not fetch_if_missing or from_currency not in FBIL_CURRENCIES:
        return None

    try:
        rows = fetch_fbil_reference_rates(
            add_days(on_date, -ON_DEMAND_LOOKBACK_DAYS), on_date, (from_currency,)
        )
    except frappe.ValidationError:
        return None

    if not rows:
        return None

    latest = rows[-1]
    upsert_currency_exchange(latest.date, latest.currency, latest.rate)
    return flt(latest.rate, RATE_PRECISION)


def set_fbil_conversion_rate(doc, method=None):
    """
    Sales Invoice `before_validate` hook.

    For Indian companies with INR as default currency, set conversion_rate to
    the FBIL reference rate (latest on or before posting_date) when the invoice
    is in a currency published by FBIL. Other currencies, opening entries and
    returns against an existing invoice keep their own rate.
    """
    if not doc.get("company") or doc.get("currency") not in FBIL_CURRENCIES:
        return

    if doc.get("is_opening") == "Yes" or (doc.get("is_return") and doc.get("return_against")):
        return

    if not is_fbil_exchange_rate_enabled():
        return

    company = frappe.get_cached_value("Company", doc.company, ("country", "default_currency"), as_dict=True)
    if not company or company.country != "India" or company.default_currency != TO_CURRENCY:
        return

    posting_date = doc.get("posting_date") or nowdate()
    rate = get_fbil_exchange_rate(doc.currency, posting_date)
    if not rate:
        frappe.throw(
            _(
                "No FBIL reference rate is available for {0} to {1} on or before {2}."
                " Run the FBIL sync or create a Currency Exchange record for this date."
            ).format(
                frappe.bold(doc.currency), frappe.bold(TO_CURRENCY), frappe.bold(formatdate(posting_date))
            ),
            title=_("Exchange Rate Not Found"),
        )

    if flt(doc.conversion_rate, RATE_PRECISION) != rate:
        doc.conversion_rate = rate


def _normalize_currencies(currencies) -> tuple[str, ...]:
    if not currencies:
        return FBIL_CURRENCIES

    if isinstance(currencies, str):
        currencies = currencies.split(",")

    return tuple(currency.strip().upper() for currency in currencies if currency and currency.strip())
