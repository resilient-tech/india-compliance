# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt
"""Constants, row definitions, and helper utilities for GSTR-9 computation."""


class GSTR9_Row:
    # Table 4 - Outward supplies (tax payable)
    TABLE_4A = "4A"
    TABLE_4B = "4B"
    TABLE_4C = "4C"
    TABLE_4D = "4D"
    TABLE_4E = "4E"
    TABLE_4F = "4F"
    TABLE_4G = "4G"
    TABLE_4G1 = "4G1"
    TABLE_4H = "4H"
    TABLE_4I = "4I"
    TABLE_4J = "4J"
    TABLE_4K = "4K"
    TABLE_4L = "4L"
    TABLE_4M = "4M"
    TABLE_4N = "4N"

    # Table 5 - Outward supplies (tax not payable)
    TABLE_5A = "5A"
    TABLE_5B = "5B"
    TABLE_5C = "5C"
    TABLE_5C1 = "5C1"
    TABLE_5D = "5D"
    TABLE_5E = "5E"
    TABLE_5F = "5F"
    TABLE_5G = "5G"
    TABLE_5H = "5H"
    TABLE_5I = "5I"
    TABLE_5J = "5J"
    TABLE_5K = "5K"
    TABLE_5L = "5L"
    TABLE_5M = "5M"
    TABLE_5N = "5N"

    # Table 6 - ITC availed
    TABLE_6A = "6A"
    TABLE_6A1 = "6A1"
    TABLE_6A2 = "6A2"
    TABLE_6B = "6B"
    TABLE_6B_INPUTS = "6B_ip"
    TABLE_6B_CAPITAL_GOODS = "6B_cg"
    TABLE_6B_INPUT_SERVICES = "6B_is"
    TABLE_6C = "6C"
    TABLE_6C_INPUTS = "6C_ip"
    TABLE_6C_CAPITAL_GOODS = "6C_cg"
    TABLE_6C_INPUT_SERVICES = "6C_is"
    TABLE_6D = "6D"
    TABLE_6D_INPUTS = "6D_ip"
    TABLE_6D_CAPITAL_GOODS = "6D_cg"
    TABLE_6D_INPUT_SERVICES = "6D_is"
    TABLE_6E = "6E"
    TABLE_6E_INPUTS = "6E_ip"
    TABLE_6E_CAPITAL_GOODS = "6E_cg"
    TABLE_6F = "6F"
    TABLE_6G = "6G"
    TABLE_6H = "6H"
    TABLE_6I = "6I"
    TABLE_6J = "6J"
    TABLE_6K = "6K"
    TABLE_6L = "6L"
    TABLE_6M = "6M"
    TABLE_6N = "6N"
    TABLE_6O = "6O"

    # Table 7 - ITC reversed
    TABLE_7A = "7A"
    TABLE_7A1 = "7A1"
    TABLE_7A2 = "7A2"
    TABLE_7B = "7B"
    TABLE_7C = "7C"
    TABLE_7D = "7D"
    TABLE_7E = "7E"
    TABLE_7F = "7F"
    TABLE_7G = "7G"
    TABLE_7H1 = "7H1"
    TABLE_7I = "7I"
    TABLE_7J = "7J"

    # Table 8 - Other ITC
    TABLE_8A = "8A"
    TABLE_8B = "8B"
    TABLE_8C = "8C"
    TABLE_8D = "8D"
    TABLE_8E = "8E"
    TABLE_8F = "8F"
    TABLE_8G = "8G"
    TABLE_8H = "8H"
    TABLE_8H1 = "8H1"
    TABLE_8I = "8I"
    TABLE_8J = "8J"
    TABLE_8K = "8K"

    # Table 9 - Tax paid (portal auto-filled, non-editable)
    TABLE_9 = "9"

    # Tables 10-14 - Previous year (manual)
    TABLE_10 = "10"
    TABLE_11 = "11"
    TABLE_10_11_TURNOVER = "10_11_turnover"  # auto-computed: 5N + 10 - 11
    TABLE_12 = "12"
    TABLE_13 = "13"
    TABLE_14 = "14"
    TABLE_14A = "14A"  # Integrated Tax sub-row
    TABLE_14B = "14B"  # Central Tax sub-row
    TABLE_14C = "14C"  # State/UT Tax sub-row
    TABLE_14D = "14D"  # Cess sub-row
    TABLE_14E = "14E"  # Interest sub-row

    # Tables 15-16 - Demands/Refunds, Composition (manual, optional)
    TABLE_15 = "15"  # nested list of 15A-15G sub-rows
    TABLE_16A = "16A"
    TABLE_16B = "16B"
    TABLE_16C = "16C"

    # Tables 17-18 - HSN
    TABLE_17 = "17"
    TABLE_18 = "18"


# Row descriptions for display
GSTR9_ROW_DESCRIPTION = {
    GSTR9_Row.TABLE_4A: "Supplies made to un-registered persons (B2C)",
    GSTR9_Row.TABLE_4B: "Supplies made to registered persons (B2B)",
    GSTR9_Row.TABLE_4C: "Zero rated supply (Export) on payment of tax (except supplies to SEZs)",
    GSTR9_Row.TABLE_4D: "Supply to SEZs on payment of tax",
    GSTR9_Row.TABLE_4E: "Deemed Exports",
    GSTR9_Row.TABLE_4F: "Advances on which tax has been paid but invoice has not been issued (not covered under (4A) to (4E) above)",
    GSTR9_Row.TABLE_4G: "Inward supplies on which tax is to be paid on reverse charge basis",
    GSTR9_Row.TABLE_4G1: "Supplies on which e-commerce operator is required to pay tax u/s 9(5) [Operator to report]",
    GSTR9_Row.TABLE_4H: "Sub-total (4A to 4G1)",
    GSTR9_Row.TABLE_4I: "Credit Notes issued in respect of transactions in (4B) to (4E)",
    GSTR9_Row.TABLE_4J: "Debit Notes issued in respect of transactions in (4B) to (4E)",
    GSTR9_Row.TABLE_4K: "Supplies / tax declared through Amendments (+)",
    GSTR9_Row.TABLE_4L: "Supplies / tax declared through Amendments (-)",
    GSTR9_Row.TABLE_4M: "Sub-total (4I to 4L)",
    GSTR9_Row.TABLE_4N: "Supplies and advances on which tax is to be paid (4H + 4M) above",
    GSTR9_Row.TABLE_5A: "Zero rated supply (Export) without payment of tax",
    GSTR9_Row.TABLE_5B: "Supply to SEZs without payment of tax",
    GSTR9_Row.TABLE_5C: "Supplies on which tax is to be paid by the recipient on reverse charge basis",
    GSTR9_Row.TABLE_5C1: "Supplies on which tax is to be paid by e-commerce operators u/s 9(5) [Supplier to report]",
    GSTR9_Row.TABLE_5D: "Exempted",
    GSTR9_Row.TABLE_5E: "Nil Rated",
    GSTR9_Row.TABLE_5F: "Non-GST supply (includes 'no supply')",
    GSTR9_Row.TABLE_5G: "Sub-total (5A to 5F)",
    GSTR9_Row.TABLE_5H: "Credit Notes issued in respect of transactions in (5A) to (5F)",
    GSTR9_Row.TABLE_5I: "Debit Notes issued in respect of transactions in (5A) to (5F)",
    GSTR9_Row.TABLE_5J: "Supplies declared through Amendments (+)",
    GSTR9_Row.TABLE_5K: "Supplies declared through Amendments (-)",
    GSTR9_Row.TABLE_5L: "Sub-total (5H to 5K)",
    GSTR9_Row.TABLE_5M: "Turnover on which tax is not to be paid  (5G + 5L) above",
    GSTR9_Row.TABLE_5N: "Total Turnover (including advances) (4N + 5M - 4G - 4G1)",
    GSTR9_Row.TABLE_6A: "Total amount of input tax credit availed through FORM GSTR-3B (Sum total of table 4A of FORM GSTR-3B)",
    GSTR9_Row.TABLE_6A1: "ITC of any preceding financial year availed in the financial year (which is included in 6A above) other than reclaim",
    GSTR9_Row.TABLE_6A2: "Net ITC of the financial year (A-A1)",
    GSTR9_Row.TABLE_6B: "Inward supplies (other than imports and inward supplies liable to reverse charge but includes services received from SEZs)",
    GSTR9_Row.TABLE_6B_INPUTS: "Inputs",
    GSTR9_Row.TABLE_6B_CAPITAL_GOODS: "Capital Goods",
    GSTR9_Row.TABLE_6B_INPUT_SERVICES: "Input Services",
    GSTR9_Row.TABLE_6C: "Inward supplies received from unregistered persons liable to reverse charge (other than B above) on which tax is paid & ITC availed",
    GSTR9_Row.TABLE_6C_INPUTS: "Inputs",
    GSTR9_Row.TABLE_6C_CAPITAL_GOODS: "Capital Goods",
    GSTR9_Row.TABLE_6C_INPUT_SERVICES: "Input Services",
    GSTR9_Row.TABLE_6D: "Inward supplies received from registered persons liable to reverse charge (other than B above) on which tax is paid and ITC availed",
    GSTR9_Row.TABLE_6D_INPUTS: "Inputs",
    GSTR9_Row.TABLE_6D_CAPITAL_GOODS: "Capital Goods",
    GSTR9_Row.TABLE_6D_INPUT_SERVICES: "Input Services",
    GSTR9_Row.TABLE_6E: "Import of goods (including supplies from SEZ)",
    GSTR9_Row.TABLE_6E_INPUTS: "Inputs",
    GSTR9_Row.TABLE_6E_CAPITAL_GOODS: "Capital Goods",
    GSTR9_Row.TABLE_6F: "Import of services (excluding inward supplies from SEZs)",
    GSTR9_Row.TABLE_6G: "Input Tax credit received from ISD",
    GSTR9_Row.TABLE_6H: "Amount of ITC reclaimed under the provisions of the Act",
    GSTR9_Row.TABLE_6I: "Sub-total (B to H above)",
    GSTR9_Row.TABLE_6J: "Difference (I - A2 above)",
    GSTR9_Row.TABLE_6K: "Transition Credit through TRAN-1 (including revisions if any)",
    GSTR9_Row.TABLE_6L: "Transition Credit through TRAN-2",
    GSTR9_Row.TABLE_6M: "ITC availed through ITC-01, ITC-02, and ITC-02A (other than GSTR-3B and TRAN Forms)",
    GSTR9_Row.TABLE_6N: "Sub-total (K to M above)",
    GSTR9_Row.TABLE_6O: "Total ITC availed (I + N) above",
    GSTR9_Row.TABLE_7A: "As per Rule 37",
    GSTR9_Row.TABLE_7A1: "As per Rule 37A",
    GSTR9_Row.TABLE_7A2: "As per Rule 38",
    GSTR9_Row.TABLE_7B: "As per Rule 39",
    GSTR9_Row.TABLE_7C: "As per Rule 42",
    GSTR9_Row.TABLE_7D: "As per Rule 43",
    GSTR9_Row.TABLE_7E: "As per section 17(5)",
    GSTR9_Row.TABLE_7F: "Reversal of TRAN-I credit",
    GSTR9_Row.TABLE_7G: "Reversal of TRAN-II credit",
    GSTR9_Row.TABLE_7H1: "Other reversals (specify)",
    GSTR9_Row.TABLE_7I: "Total ITC Reversed (A to H)",
    GSTR9_Row.TABLE_7J: "Net ITC Available for Utilization (6O - 7I)",
    GSTR9_Row.TABLE_8A: "ITC as per GSTR-2B",
    GSTR9_Row.TABLE_8B: "ITC as per sum total of 6B above",
    GSTR9_Row.TABLE_8C: (
        "ITC on inward supplies (other than imports and inward supplies liable to reverse"
        " charge but includes services received from SEZs) received during the financial"
        " year but availed in the next financial year upto specified period"
    ),
    GSTR9_Row.TABLE_8D: "Difference [8A - (8B + 8C)]",
    GSTR9_Row.TABLE_8E: "ITC available but not availed",
    GSTR9_Row.TABLE_8F: "ITC available but ineligible",
    GSTR9_Row.TABLE_8G: "IGST paid  on import of goods (including supplies from SEZ)",
    GSTR9_Row.TABLE_8H: "IGST credit availed on import of goods (as per 6(E) above) in financial year",
    GSTR9_Row.TABLE_8H1: "IGST Credit availed on Import of goods in next financial year",
    GSTR9_Row.TABLE_8I: "Difference (8G - 8H - 8H1)",
    GSTR9_Row.TABLE_8J: "ITC available but not availed on import of goods (Equal to 8I)",
    GSTR9_Row.TABLE_8K: "Total ITC to be lapsed in current financial year (8E + 8F + 8J)",
    GSTR9_Row.TABLE_9: "Details of tax paid as declared in returns filed during the financial year",
    GSTR9_Row.TABLE_10: "Supplies / tax declared through Debit Notes (+)",
    GSTR9_Row.TABLE_11: "Supplies / tax reduced through Credit Notes (-)",
    GSTR9_Row.TABLE_10_11_TURNOVER: "Total Turnover (5N + 10 - 11)",
    GSTR9_Row.TABLE_12: "Reversal of ITC availed during previous financial year",
    GSTR9_Row.TABLE_13: "ITC availed for the previous financial year",
    GSTR9_Row.TABLE_14: "Differential tax paid on account of declaration in Table 10 & 11",
    GSTR9_Row.TABLE_15: "Particulars of Demands and Refunds",
    GSTR9_Row.TABLE_16A: "Inward supplies received from composition taxpayers",
    GSTR9_Row.TABLE_16B: "Deemed supply under Section 143(3) and (5) by Job Worker",
    GSTR9_Row.TABLE_16C: "Goods sent on approval basis but not returned within 6 months",
    GSTR9_Row.TABLE_17: "HSN-wise summary of outward supplies",
    GSTR9_Row.TABLE_18: "HSN-wise summary of inward supplies",
}

# Rows sourced from portal (non-editable, require download)
PORTAL_SOURCED_ROWS = frozenset({GSTR9_Row.TABLE_6A, GSTR9_Row.TABLE_8A, GSTR9_Row.TABLE_9})

# Rows whose invoice detail comes from Purchase Invoices / BOE (not Sales Invoices)
PURCHASE_ROW_KEYS = frozenset(
    {
        GSTR9_Row.TABLE_4G,
        GSTR9_Row.TABLE_6B,
        GSTR9_Row.TABLE_6B_INPUTS,
        GSTR9_Row.TABLE_6B_CAPITAL_GOODS,
        GSTR9_Row.TABLE_6B_INPUT_SERVICES,
        GSTR9_Row.TABLE_6C,
        GSTR9_Row.TABLE_6C_INPUTS,
        GSTR9_Row.TABLE_6C_CAPITAL_GOODS,
        GSTR9_Row.TABLE_6C_INPUT_SERVICES,
        GSTR9_Row.TABLE_6D,
        GSTR9_Row.TABLE_6D_INPUTS,
        GSTR9_Row.TABLE_6D_CAPITAL_GOODS,
        GSTR9_Row.TABLE_6D_INPUT_SERVICES,
        GSTR9_Row.TABLE_6E,
        GSTR9_Row.TABLE_6E_INPUTS,
        GSTR9_Row.TABLE_6E_CAPITAL_GOODS,
        GSTR9_Row.TABLE_6F,
        GSTR9_Row.TABLE_6G,
    }
)

# Standard amount columns for Tables 4-8
AMOUNT_FIELDS = ("taxable_value", "igst", "cgst", "sgst", "cess")

# Auto-computation formulas
AUTO_COMPUTE_FORMULAS = {
    GSTR9_Row.TABLE_4H: lambda d: _sum_rows(
        d,
        [
            GSTR9_Row.TABLE_4A,
            GSTR9_Row.TABLE_4B,
            GSTR9_Row.TABLE_4C,
            GSTR9_Row.TABLE_4D,
            GSTR9_Row.TABLE_4E,
            GSTR9_Row.TABLE_4F,
            GSTR9_Row.TABLE_4G,
            GSTR9_Row.TABLE_4G1,
        ],
    ),
    # 4I (credit notes) is stored as a positive amount and subtracted, matching the portal convention
    GSTR9_Row.TABLE_4M: lambda d: _sum_rows(
        d,
        [
            GSTR9_Row.TABLE_4J,
            GSTR9_Row.TABLE_4K,
        ],
        subtract=[GSTR9_Row.TABLE_4I, GSTR9_Row.TABLE_4L],
    ),
    GSTR9_Row.TABLE_4N: lambda d: _sum_rows(d, [GSTR9_Row.TABLE_4H, GSTR9_Row.TABLE_4M]),
    GSTR9_Row.TABLE_5G: lambda d: _sum_rows(
        d,
        [
            GSTR9_Row.TABLE_5A,
            GSTR9_Row.TABLE_5B,
            GSTR9_Row.TABLE_5C,
            GSTR9_Row.TABLE_5C1,
            GSTR9_Row.TABLE_5D,
            GSTR9_Row.TABLE_5E,
            GSTR9_Row.TABLE_5F,
        ],
    ),
    # 5H (credit notes) is stored as a positive amount and subtracted, matching the portal convention
    GSTR9_Row.TABLE_5L: lambda d: _sum_rows(
        d,
        [
            GSTR9_Row.TABLE_5I,
            GSTR9_Row.TABLE_5J,
        ],
        subtract=[GSTR9_Row.TABLE_5H, GSTR9_Row.TABLE_5K],
    ),
    GSTR9_Row.TABLE_5M: lambda d: _sum_rows(d, [GSTR9_Row.TABLE_5G, GSTR9_Row.TABLE_5L]),
    GSTR9_Row.TABLE_5N: lambda d: _sum_rows(
        d,
        [
            GSTR9_Row.TABLE_4N,
            GSTR9_Row.TABLE_5M,
        ],
        subtract=[GSTR9_Row.TABLE_4G, GSTR9_Row.TABLE_4G1],
    ),
    GSTR9_Row.TABLE_10_11_TURNOVER: lambda d: _sum_rows(
        d,
        [
            GSTR9_Row.TABLE_5N,
            GSTR9_Row.TABLE_10,
        ],
        subtract=[GSTR9_Row.TABLE_11],
    ),
    GSTR9_Row.TABLE_6A2: lambda d: _sum_rows(d, [GSTR9_Row.TABLE_6A], subtract=[GSTR9_Row.TABLE_6A1]),
    GSTR9_Row.TABLE_6B: lambda d: _sum_rows(
        d,
        [
            GSTR9_Row.TABLE_6B_INPUTS,
            GSTR9_Row.TABLE_6B_CAPITAL_GOODS,
            GSTR9_Row.TABLE_6B_INPUT_SERVICES,
        ],
    ),
    GSTR9_Row.TABLE_6C: lambda d: _sum_rows(
        d,
        [
            GSTR9_Row.TABLE_6C_INPUTS,
            GSTR9_Row.TABLE_6C_CAPITAL_GOODS,
            GSTR9_Row.TABLE_6C_INPUT_SERVICES,
        ],
    ),
    GSTR9_Row.TABLE_6D: lambda d: _sum_rows(
        d,
        [
            GSTR9_Row.TABLE_6D_INPUTS,
            GSTR9_Row.TABLE_6D_CAPITAL_GOODS,
            GSTR9_Row.TABLE_6D_INPUT_SERVICES,
        ],
    ),
    GSTR9_Row.TABLE_6E: lambda d: _sum_rows(
        d,
        [
            GSTR9_Row.TABLE_6E_INPUTS,
            GSTR9_Row.TABLE_6E_CAPITAL_GOODS,
        ],
    ),
    GSTR9_Row.TABLE_6I: lambda d: _sum_rows(
        d,
        [
            GSTR9_Row.TABLE_6B,
            GSTR9_Row.TABLE_6C,
            GSTR9_Row.TABLE_6D,
            GSTR9_Row.TABLE_6E,
            GSTR9_Row.TABLE_6F,
            GSTR9_Row.TABLE_6G,
            GSTR9_Row.TABLE_6H,
        ],
    ),
    GSTR9_Row.TABLE_6J: lambda d: _sum_rows(d, [GSTR9_Row.TABLE_6I], subtract=[GSTR9_Row.TABLE_6A2]),
    GSTR9_Row.TABLE_6N: lambda d: _sum_rows(d, [GSTR9_Row.TABLE_6K, GSTR9_Row.TABLE_6L, GSTR9_Row.TABLE_6M]),
    GSTR9_Row.TABLE_6O: lambda d: _sum_rows(d, [GSTR9_Row.TABLE_6I, GSTR9_Row.TABLE_6N]),
    GSTR9_Row.TABLE_7I: lambda d: _sum_rows(
        d,
        [
            GSTR9_Row.TABLE_7A,
            GSTR9_Row.TABLE_7A1,
            GSTR9_Row.TABLE_7A2,
            GSTR9_Row.TABLE_7B,
            GSTR9_Row.TABLE_7C,
            GSTR9_Row.TABLE_7D,
            GSTR9_Row.TABLE_7E,
            GSTR9_Row.TABLE_7F,
            GSTR9_Row.TABLE_7G,
            GSTR9_Row.TABLE_7H1,
        ],
    ),
    GSTR9_Row.TABLE_7J: lambda d: _sum_rows(d, [GSTR9_Row.TABLE_6O], subtract=[GSTR9_Row.TABLE_7I]),
    GSTR9_Row.TABLE_8B: lambda d: d.get(GSTR9_Row.TABLE_6B, _empty_row()),
    GSTR9_Row.TABLE_8D: lambda d: _sum_rows(
        d, [GSTR9_Row.TABLE_8A], subtract=[GSTR9_Row.TABLE_8B, GSTR9_Row.TABLE_8C]
    ),
    GSTR9_Row.TABLE_8H: lambda d: d.get(GSTR9_Row.TABLE_6E, _empty_row()),
    GSTR9_Row.TABLE_8I: lambda d: _sum_rows(
        d, [GSTR9_Row.TABLE_8G], subtract=[GSTR9_Row.TABLE_8H, GSTR9_Row.TABLE_8H1]
    ),
    GSTR9_Row.TABLE_8J: lambda d: d.get(GSTR9_Row.TABLE_8I, _empty_row()),
    GSTR9_Row.TABLE_8K: lambda d: _sum_rows(d, [GSTR9_Row.TABLE_8E, GSTR9_Row.TABLE_8F, GSTR9_Row.TABLE_8J]),
}


def _empty_row():
    return {field: 0 for field in AMOUNT_FIELDS}


def _sum_rows(data, add_rows, subtract=None):
    result = _empty_row()
    for row_key in add_rows:
        row = data.get(row_key, _empty_row())
        for field in AMOUNT_FIELDS:
            result[field] += row.get(field, 0)

    for row_key in subtract or []:
        row = data.get(row_key, _empty_row())
        for field in AMOUNT_FIELDS:
            result[field] -= row.get(field, 0)

    return result


def compute_auto_rows(data):
    """Compute all auto-computed rows in dependency order.

    data is a dict of {row_key: {field: value, ...}}
    """
    # Compute in defined order (formulas dict is insertion-ordered in Python 3.7+)
    for row_key, formula in AUTO_COMPUTE_FORMULAS.items():
        data[row_key] = formula(data)

    return data


# Rows whose amounts are derived from credit note documents (negative in ERP).
# After aggregation these are negated so they display and compare as positive values,
# matching the portal convention where credit notes are shown as positive and subtracted
# in the sub-total formula.
CREDIT_NOTE_ROWS = frozenset({GSTR9_Row.TABLE_4I, GSTR9_Row.TABLE_5H})


def aggregate_books(books):
    """
    Aggregate invoice-level books data into row-level amount dicts.

    Books format:
      {row_key: {doc_number: invoice_dict}}  — drillable invoice rows
      {row_key: {amount_fields}}             — already-aggregated rows
      {row_key: list}                        — Table 14/15/17/18 structures

    For drillable rows the invoice dicts are summed across AMOUNT_FIELDS.
    Credit note rows (4I, 5H) have their sign flipped after summation so
    the stored value is a positive absolute amount (portal convention).
    """
    from frappe.utils import flt

    result = {}
    for row_key, value in books.items():
        if isinstance(value, dict):
            first_val = next(iter(value.values()), None)
            if first_val is None:
                # empty invoice dict → empty row
                result[row_key] = _empty_row()
            elif isinstance(first_val, dict) and "total_taxable_value" in first_val:
                # Drillable row: {doc_num: inv_dict} with total_* amount fields
                row = _empty_row()
                for inv in value.values():
                    row["taxable_value"] += flt(inv.get("total_taxable_value", 0))
                    row["igst"] += flt(inv.get("total_igst_amount", 0))
                    row["cgst"] += flt(inv.get("total_cgst_amount", 0))
                    row["sgst"] += flt(inv.get("total_sgst_amount", 0))
                    row["cess"] += flt(inv.get("total_cess_amount", 0))
                result[row_key] = row
            else:
                # Already aggregated ({field: value}) or
                # Table 17/18 ({"goods": [...], "services": [...]}) — pass through
                result[row_key] = value
        elif isinstance(value, list):
            if not value:
                result[row_key] = _empty_row()
            else:
                # Table 14/15 structured lists — pass through
                result[row_key] = value
        else:
            result[row_key] = value

    # Credit note rows are stored as negative in ERP; negate to make them positive
    for row_key in CREDIT_NOTE_ROWS:
        if row_key in result and isinstance(result[row_key], dict):
            result[row_key] = {f: -result[row_key][f] for f in AMOUNT_FIELDS}

    return result


def get_fy_dates(financial_year):
    """Get from_date and to_date for a financial year string.

    e.g. "2024-25" → (date(2024, 4, 1), date(2025, 3, 31))
    """
    from frappe.utils import getdate

    start_year = int(financial_year.split("-")[0])
    from_date = getdate(f"{start_year}-04-01")
    to_date = getdate(f"{start_year + 1}-03-31")
    return from_date, to_date


def get_fy_period(financial_year):
    """
    Convert financial year to return_period format for GST Return Log naming.
    e.g. "2024-25" → "202425"
    """
    return financial_year.replace("-", "")


def get_gstr9_return_period(financial_year):
    """
    Convert financial year to GSTN GSTR-9 API ret_period (MMYYYY).
    GSTR-9 always ends in March of the closing year.
    e.g. "2024-25" → "032025"
    """
    start_year = int(financial_year.split("-")[0])
    return f"03{start_year + 1}"
