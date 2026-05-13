# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

from india_compliance.gst_india.api_classes.taxpayer_returns import GSTR9API
from india_compliance.gst_india.utils.gstr_9 import (
    PORTAL_SOURCED_ROWS,
    GSTR9_Row,
    _empty_row,
    get_fy_schema,
    get_gstr9_return_period,
)


def download_gstr9_data(gstr9_log, filters):
    """Download auto-drafted GSTR-9 data from the GST portal."""
    api = GSTR9API(gstr9_log.gstin, get_gstr9_return_period(filters.financial_year))
    return convert_portal_data(api.get_data(), filters.financial_year)


def convert_portal_data(response, financial_year):
    """Convert GSTN API response to {row_key: amount_dict}."""
    data = {}
    portal_row_map = get_fy_schema(financial_year).portal_row_map

    for row_key, (table_key, portal_key) in portal_row_map.items():
        row_data = response.get(table_key, {}).get(portal_key)
        if row_data:
            data[row_key] = _parse_amount_row(row_data)

    table9 = response.get("table9", {})
    if table9:
        data[GSTR9_Row.TABLE_9] = _parse_table_9(table9)

    # Ensure portal-sourced rows are always present (even if absent from response)
    for row_key in PORTAL_SOURCED_ROWS:
        data.setdefault(row_key, _empty_row())

    return data


def _parse_amount_row(row_data):
    return {
        "taxable_value": row_data.get("txval", 0),
        "igst": row_data.get("iamt", 0),
        "cgst": row_data.get("camt", 0),
        "sgst": row_data.get("samt", 0),
        "cess": row_data.get("csamt", 0),
    }


def _parse_table_9(table9_data):
    """Parse Table 9 (tax paid details).

    Portal head keys: iamt, camt, samt, csamt, intr, fee, pnlty, others
    Each head object: txpyble, txpaid_cash,
                      tax_paid_itc_iamt/camt/samt/csamt
    """
    TAX_HEAD_ROWS = [
        ("iamt", "Integrated Tax", "A"),
        ("camt", "Central Tax", "B"),
        ("samt", "State/UT Tax", "C"),
        ("csamt", "Cess", "D"),
        ("intr", "Interest", "E"),
        ("fee", "Late Fee", "F"),
        ("pnlty", "Penalty", "G"),
        ("others", "Other", "H"),
    ]

    result = []
    for head_key, label, row_label in TAX_HEAD_ROWS:
        head = table9_data.get(head_key) or {}
        tax_payable = head.get("txpyble", 0)
        paid_cash = head.get("txpaid_cash", 0)
        itc_igst = head.get("tax_paid_itc_iamt", 0)
        itc_cgst = head.get("tax_paid_itc_camt", 0)
        itc_sgst = head.get("tax_paid_itc_samt", 0)
        itc_cess = head.get("tax_paid_itc_csamt", 0)
        total_paid = paid_cash + itc_igst + itc_cgst + itc_sgst + itc_cess

        result.append(
            {
                "row_label": row_label,
                "tax_head": label,
                "tax_payable": tax_payable,
                "paid_through_cash": paid_cash,
                "itc_igst": itc_igst,
                "itc_cgst": itc_cgst,
                "itc_sgst": itc_sgst,
                "itc_cess": itc_cess,
                "total_paid": total_paid,
                "difference": tax_payable - total_paid,
            }
        )

    return result
