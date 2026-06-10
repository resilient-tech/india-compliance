# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import add_days, add_years, getdate

from india_compliance.income_tax_india.constants import (
    MSME_APPLICABLE_TYPES,
    MSME_PAYMENT_DAYS,
)


def get_indian_fiscal_year(date) -> str:
    """Return the Indian income-tax FY (April-March) for a date, e.g. "2024-2025"."""
    date = getdate(date)
    start_year = date.year if date.month >= 4 else date.year - 1
    return f"{start_year}-{start_year + 1}"


def get_msme_due_date(posting_date) -> str:
    """MSME payment due date: posting date (treated as date of acceptance) + 45 days."""
    return add_days(getdate(posting_date), MSME_PAYMENT_DAYS)


def is_section_43_b_msme_applicable(enterprise_type, is_trader) -> bool:
    """Section 43B(h) applies only to Micro/Small enterprises that are not traders."""
    return bool(enterprise_type in MSME_APPLICABLE_TYPES and not is_trader)


def get_classification_map(
    suppliers: list[str], financial_years: list[str] | None = None
) -> dict[tuple, dict]:
    """Bulk-load classification rows for suppliers, keyed by (supplier, fy).

    Pass ``financial_years`` to fetch only the years actually needed (e.g. the
    FYs spanned by the invoices under report) instead of every year on record.
    """
    filters = {"parenttype": "Supplier", "parent": ("in", suppliers)}
    if financial_years:
        filters["financial_year"] = ("in", financial_years)

    rows = frappe.get_all(
        "India MSME Classification",
        filters=filters,
        fields=["parent as supplier", "financial_year", "enterprise_type"],
    )
    return {(row.supplier, row.financial_year): row for row in rows}


def get_fiscal_year_dates(financial_year: str) -> tuple:
    """Return (start_date, end_date) for an Indian FY string like "2024-2025"."""
    start = getdate(f"{int(financial_year.split('-')[0])}-04-01")
    return start, add_days(add_years(start, 1), -1)  # 1 Apr -> 31 Mar next year


def get_financial_years_between(from_date, to_date) -> list[str]:
    """Indian FY strings spanned by a date range, e.g. ["2023-2024", "2024-2025"]."""
    start_year = int(get_indian_fiscal_year(from_date).split("-")[0])
    end_year = int(get_indian_fiscal_year(to_date).split("-")[0])
    return [f"{year}-{year + 1}" for year in range(start_year, end_year + 1)]
