# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _, bold

from india_compliance.income_tax_india.constants import (
    FINANCIAL_YEAR_REGEX,
    UDYAM_NUMBER_REGEX,
)
from india_compliance.income_tax_india.utils.msme import is_section_43_b_msme_applicable


def validate(doc, method=None):
    validate_udyam_number(doc)
    validate_msme_classifications(doc)


def validate_udyam_number(doc):
    if not doc.get("udyam_number"):
        return

    doc.udyam_number = doc.udyam_number.strip().upper()

    if not UDYAM_NUMBER_REGEX.match(doc.udyam_number):
        frappe.throw(
            _("{0} is not a valid UDYAM Registration Number. Expected format: UDYAM-XX-00-0000000").format(
                bold(doc.udyam_number)
            ),
            title=_("Invalid UDYAM Number"),
        )


def validate_msme_classifications(doc):
    """Validate year-wise classification rows and persist 43B(h) applicability.

    Applicable = Micro/Small enterprise that is not a trader. The financial year
    must be a valid Indian FY string (two consecutive years, e.g. 2024-2025).
    """
    seen_years = set()
    for row in doc.get("india_msme_classification") or []:
        validate_financial_year(row)

        if row.financial_year in seen_years:
            frappe.throw(
                _("Row #{0}: Duplicate MSME classification for Financial Year {1}").format(
                    row.idx, bold(row.financial_year)
                )
            )
        seen_years.add(row.financial_year)

        row.msme_applicable = is_section_43_b_msme_applicable(row.enterprise_type, doc.msme_is_trader)


def validate_financial_year(row):
    fy = row.financial_year or ""

    # must look like "YYYY-YYYY" with consecutive years, e.g. 2024-2025
    if FINANCIAL_YEAR_REGEX.match(fy) and int(fy[5:]) == int(fy[:4]) + 1:
        return

    frappe.throw(
        _(
            "Row #{0}: {1} is not a valid Financial Year. Expected two consecutive years, e.g. 2024-2025"
        ).format(row.idx, bold(row.financial_year)),
        title=_("Invalid Financial Year"),
    )
