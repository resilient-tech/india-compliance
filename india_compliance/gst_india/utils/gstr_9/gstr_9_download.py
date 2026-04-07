# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

from india_compliance.gst_india.api_classes.taxpayer_returns import GSTR9API
from india_compliance.gst_india.utils.gstr_9 import (
    PORTAL_SOURCED_ROWS,
    GSTR9_Row,
    _empty_row,
    get_gstr9_return_period,
)

PORTAL_TABLE_MAP = {
    "table4": {
        GSTR9_Row.TABLE_4A: "b2c",
        GSTR9_Row.TABLE_4B: "b2b",
        GSTR9_Row.TABLE_4C: "exp",
        GSTR9_Row.TABLE_4D: "sez",
        GSTR9_Row.TABLE_4E: "deemed",
        GSTR9_Row.TABLE_4F: "at",  # advance tax
        GSTR9_Row.TABLE_4G: "rchrg",  # inward RCM
        GSTR9_Row.TABLE_4G1: "ecom",  # e-commerce 9(5)
        GSTR9_Row.TABLE_4I: "cr_nt",
        GSTR9_Row.TABLE_4J: "dr_nt",
        GSTR9_Row.TABLE_4K: "amd_pos",
        GSTR9_Row.TABLE_4L: "amd_neg",
    },
    "table5": {
        GSTR9_Row.TABLE_5A: "zero_rtd",
        GSTR9_Row.TABLE_5B: "sez",
        GSTR9_Row.TABLE_5C: "rchrg",
        GSTR9_Row.TABLE_5C1: "ecom_14",  # e-commerce 9(5) supplier-side
        GSTR9_Row.TABLE_5D: "exmt",
        GSTR9_Row.TABLE_5E: "nil",
        GSTR9_Row.TABLE_5F: "non_gst",
        GSTR9_Row.TABLE_5H: "cr_nt",
        GSTR9_Row.TABLE_5I: "dr_nt",
        GSTR9_Row.TABLE_5J: "amd_pos",
        GSTR9_Row.TABLE_5K: "amd_neg",
    },
    "table6": {
        # Simple objects
        GSTR9_Row.TABLE_6A: "itc_3b",
        GSTR9_Row.TABLE_6F: "ios",
        GSTR9_Row.TABLE_6G: "isd",
        GSTR9_Row.TABLE_6H: "itc_clmd",
        GSTR9_Row.TABLE_6K: "tran1",
        GSTR9_Row.TABLE_6L: "tran2",
        # Arrays with itc_typ breakdown — handled separately in convert_portal_data
        GSTR9_Row.TABLE_6B: "supp_non_rchrg",
        GSTR9_Row.TABLE_6C: "supp_rchrg_unreg",
        GSTR9_Row.TABLE_6D: "supp_rchrg_reg",
        GSTR9_Row.TABLE_6E: "iog",
    },
    "table8": {
        GSTR9_Row.TABLE_8A: "itc_2b",
    },
    # table9 keys are handled separately in _parse_table_9
}


def download_gstr9_data(gstr9_log, filters):
    """
    Download auto-drafted GSTR-9 data from the GST portal.

    Returns a dict of row_key → amounts for portal-sourced rows.
    """
    api = GSTR9API(gstr9_log.gstin, get_gstr9_return_period(filters.financial_year))
    return convert_portal_data(api.get_data())


# Table 6 rows whose API value is an array of {itc_typ, iamt, camt, samt, csamt}
_TABLE6_ARRAY_ROWS = {
    GSTR9_Row.TABLE_6B,
    GSTR9_Row.TABLE_6C,
    GSTR9_Row.TABLE_6D,
    GSTR9_Row.TABLE_6E,
}

# Map portal itc_typ code → sub-row suffix
_ITC_TYP_SUFFIX = {"ip": "_ip", "cg": "_cg", "is": "_is"}


def convert_portal_data(response):
    """
    Convert GSTN API response to internal row-based format.
    """
    data = {}

    for table_key, mapping in PORTAL_TABLE_MAP.items():
        table_data = response.get(table_key, {})
        if not table_data:
            continue

        for row_key, portal_key in mapping.items():
            row_data = table_data.get(portal_key)
            if not row_data:
                continue

            if row_key in _TABLE6_ARRAY_ROWS:
                sub_rows = _parse_itc_array_sub_rows(row_data, row_key)
                data.update(sub_rows)
            else:
                data[row_key] = _parse_amount_row(row_data)

    # Table 9 — tax-head objects sit directly in table9
    table9 = response.get("table9", {})
    if table9:
        data[GSTR9_Row.TABLE_9] = _parse_table_9(table9)

    # Initialize portal-sourced rows absent from the response
    for row_key in PORTAL_SOURCED_ROWS:
        if row_key not in data and row_key != GSTR9_Row.TABLE_9:
            data[row_key] = _empty_row()

    return data


def _parse_amount_row(row_data):
    """Parse a standard amount row from portal response."""
    if isinstance(row_data, dict):
        return {
            "taxable_value": row_data.get("txval", 0),
            "igst": row_data.get("iamt", 0),
            "cgst": row_data.get("camt", 0),
            "sgst": row_data.get("samt", 0),
            "cess": row_data.get("csamt", 0),
        }

    return _empty_row()


def _parse_itc_array_sub_rows(row_data, row_key):
    """
    Parse a Table 6 ITC array into sub-rows keyed by itc_typ.
    e.g. 6B → {"6B_ip": {...}, "6B_cg": {...}, "6B_is": {...}}
    Each element: {itc_typ: "ip"/"cg"/"is", iamt, camt, samt, csamt}
    Note: taxable_value is not applicable for ITC rows.
    """
    result = {}

    if not isinstance(row_data, list):
        return result

    for entry in row_data:
        itc_typ = (entry.get("itc_typ") or "").lower()
        suffix = _ITC_TYP_SUFFIX.get(itc_typ)
        if not suffix:
            continue

        sub_key = f"{row_key}{suffix}"
        if sub_key not in result:
            result[sub_key] = _empty_row()

        result[sub_key]["igst"] += entry.get("iamt", 0)
        result[sub_key]["cgst"] += entry.get("camt", 0)
        result[sub_key]["sgst"] += entry.get("samt", 0)
        result[sub_key]["cess"] += entry.get("csamt", 0)

    return result


def _parse_table_9(table9_data):
    """
    Parse Table 9 (tax paid details) from CALRCDS portal response.

    Portal rows: A=IGST, B=CGST, C=SGST/UTGST, D=Cess, E=Interest, F=Late Fee,
                 G=Penalty, H=Other
    API head keys: iamt, camt, samt, csamt, intr, fee, pnlty, others

    Each head object has:
      txpyble          — tax payable
      txpaid_cash      — paid through cash
      tax_paid_itc_iamt/camt/samt/csamt — ITC paid using each tax head

    Stored per row:
      tax_head, tax_payable, paid_through_cash,
      itc_igst, itc_cgst, itc_sgst, itc_cess,
      total_paid, difference
    """
    # (api_key, display_label, row_label)
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
    if not isinstance(table9_data, dict):
        return result

    for head_key, label, row_label in TAX_HEAD_ROWS:
        head_data = table9_data.get(head_key) or {}

        tax_payable = head_data.get("txpyble", 0)
        paid_through_cash = head_data.get("txpaid_cash", 0)
        itc_igst = head_data.get("tax_paid_itc_iamt", 0)
        itc_cgst = head_data.get("tax_paid_itc_camt", 0)
        itc_sgst = head_data.get("tax_paid_itc_samt", 0)
        itc_cess = head_data.get("tax_paid_itc_csamt", 0)
        total_itc = itc_igst + itc_cgst + itc_sgst + itc_cess
        total_paid = paid_through_cash + total_itc
        difference = tax_payable - total_paid

        result.append(
            {
                "row_label": row_label,
                "tax_head": label,
                "tax_payable": tax_payable,
                "paid_through_cash": paid_through_cash,
                "itc_igst": itc_igst,
                "itc_cgst": itc_cgst,
                "itc_sgst": itc_sgst,
                "itc_cess": itc_cess,
                "total_paid": total_paid,
                "difference": difference,
            }
        )

    return result
