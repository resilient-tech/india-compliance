# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

"""
Export GSTR-2A / 2B to the government Excel format, byte-for-byte.

The bundled portal template is filled from the stored raw portal payload (`docdata`),
not from GST Inward Supply, so every column the portal shows is preserved. Columns are
placed by header label (read from each sheet's merged header stack at runtime), so
nothing is hard-coded to a position. 2A and 2B have their own field maps: 2B expands
codes and is invoice-level; 2A keeps raw codes and is item-level with a per-invoice
"-Total" row. Empty sections stay blank, exactly like the portal file.
"""

import re
from functools import partial

import frappe
from frappe.utils import flt

from india_compliance.gst_india.constants import GST_CATEGORY_MAP, STATE_NUMBERS
from india_compliance.gst_india.doctype.gst_return_log.gst_return_log import (
    get_raw_return_data,
)
from india_compliance.gst_india.utils import get_data_file_path
from india_compliance.gst_india.utils.exporter import ExcelExporter
from india_compliance.gst_india.utils.gstr_2.gstr_2a import map_date_format
from india_compliance.gst_india.utils.gstr_utils import ReturnType
from india_compliance.gst_india.utils.returns_export import merge_raw

TEMPLATES = {
    ReturnType.GSTR2A.value: "gstr2a_excel_template_v1.0.xlsx",
    ReturnType.GSTR2B.value: "gstr2b_excel_template_v1.0.xlsx",
}

SECTION_SHEETS = {
    ReturnType.GSTR2A.value: {
        "B2B": "B2B",
        "B2BA": "B2BA",
        "CDNR": "CDNR",
        "CDNRA": "CDNRA",
        "ECO": "ECO",
        "ECOA": "ECOA",
        "ISD": "ISD",
        "IMPG": "IMPG",
        "IMPGSEZ": "IMPG SEZ",
        "TDS": "TDS",
        "TCS": "TCS",
    },
}

RETURN_TYPE_MAP = {"GSTR-2A": ReturnType.GSTR2A.value, "GSTR-2B": ReturnType.GSTR2B.value}

HEADER_START_ROW = 5
_REVISED = "revised details | "
_ORIGINAL = "original details | "
_WS = re.compile(r"\s+")
_NUMBER_TO_STATE = {number: name for name, number in STATE_NUMBERS.items()}


def _reformat_date(value, source_format, target_format):
    """Convert a date string between formats, passing empty/mismatched values through."""
    try:
        return map_date_format(value, source_format, target_format) or ""
    except (ValueError, TypeError):
        return value or ""


def _norm(value):
    """Normalize a header cell for matching: drop (₹)/(%), collapse spaces, lowercase."""
    if value is None:
        return ""
    value = re.sub(r"\(₹\)|\(%\)|₹", "", str(value))
    return _WS.sub(" ", value).strip().lower()


def _merged_value(ws, row, col):
    for rng in ws.merged_cells.ranges:
        if rng.min_row <= row <= rng.max_row and rng.min_col <= col <= rng.max_col:
            return ws.cell(rng.min_row, rng.min_col).value
    return ws.cell(row, col).value


def _header_extent(ws):
    """(header rows, data-start row) — headers run from row 5 to the first empty row."""
    row = HEADER_START_ROW
    while row <= ws.max_row:
        if all(_merged_value(ws, row, c) in (None, "") for c in range(1, ws.max_column + 1)):
            break
        row += 1
    return list(range(HEADER_START_ROW, row)), row


def _column_labels(ws, header_rows):
    """Column -> combined header label (tiers joined, consecutive duplicates collapsed)."""
    labels = {}
    for col in range(1, ws.max_column + 1):
        parts = []
        for r in header_rows:
            value = _norm(_merged_value(ws, r, col))
            if value and (not parts or parts[-1] != value):
                parts.append(value)
        labels[col] = " | ".join(parts)
    return labels


def _split_label(label):
    """(base_label, is_original) — strip a 'revised details |'/'original details |' prefix.
    Amendment sheets prefix each column so the same field map serves both blocks."""
    if label.startswith(_ORIGINAL):
        return label[len(_ORIGINAL) :], True
    if label.startswith(_REVISED):
        return label[len(_REVISED) :], False
    return label, False


def _normalize_return_type(return_type):
    """Accept the UI label ('GSTR-2B'), the enum value ('GSTR2b'), or the member."""
    if isinstance(return_type, ReturnType):
        return return_type.value
    return RETURN_TYPE_MAP.get(return_type, return_type)


def _as_section_dict(obj):
    """Unwrap a docdata sub-section (itcrev / docRejdata) that may arrive list-wrapped."""
    if isinstance(obj, list):
        return obj[0] if obj else {}
    return obj or {}


def _merged_raw(gstin, return_type, periods):
    """The stored payload merged across periods (section lists concatenated)."""
    merged = {}
    for period in periods:
        raw = get_raw_return_data(gstin, return_type, period)
        if isinstance(raw, dict):
            merged = merge_raw(merged, raw)
    return merged


def _rdate(value):  # "DD-MM-YYYY" -> "DD/MM/YYYY"
    return _reformat_date(value, "%d-%m-%Y", "%d/%m/%Y")


def _rperiod(value):  # "MMYYYY" -> "Apr'26"
    return _reformat_date(value, "%m%Y", "%b'%y")


def _financial_year(period):  # "MMYYYY" -> "2019-20" (Indian FY starts in April)
    month, year = int(period[:2]), int(period[2:])
    start = year if month >= 4 else year - 1
    return f"{start}-{str(start + 1)[-2:]}"


def _ryesno(value):
    return {"Y": "Yes", "N": "No"}.get(value, "")


def _ritc(value):
    return {"Y": "Yes", "N": "No", "T": "Temporary"}.get(value, "")


def _rstate(value):
    return _NUMBER_TO_STATE.get(str(value).zfill(2), value or "") if value else ""


def _rpct(value):
    return f"{flt(1 if value is None else value) * 100:g}%"


def _rtype(value):
    return GST_CATEGORY_MAP.get(value, value or "")


def _rnote(value):
    return {"C": "Credit Note", "D": "Debit Note"}.get(value, value or "")


def _risd(value):
    return {"ISDI": "ISD Invoice", "ISDC": "ISD Credit Note"}.get(value, value or "")


_ITC_REASON = {
    "P": "POS and supplier state are same but recipient state is different",
    "C": "Return filed post annual cut-off",
}


def _rreason(value):
    return _ITC_REASON.get(value, "")


RAW_FIELDS_2B = {
    "gstin of supplier": ("s", "ctin", None),
    "gstin of isd": ("s", "ctin", None),
    "trade/legal name": ("s", "trdnm", None),
    "gstin of eco": ("s", "ctin", None),
    "gstr-1/1a/iff/gstr-5 period": ("s", "supprd", _rperiod),
    "gstr-1/iff/1a/gstr-5 period": ("s", "supprd", _rperiod),
    "gstr-1/1a/iff period": ("s", "supprd", _rperiod),
    "gstr-1/iff/1a period": ("s", "supprd", _rperiod),
    "gstr-1/iff/gstr-1a period": ("s", "supprd", _rperiod),
    "isd gstr-6 period": ("s", "supprd", _rperiod),
    "gstr-1/1a/iff/gstr-5 filing date": ("s", "supfildt", _rdate),
    "gstr-1/iff/1a/gstr-5 filing date": ("s", "supfildt", _rdate),
    "gstr-1/1a/iff filing date": ("s", "supfildt", _rdate),
    "gstr-1/iff/1a filing date": ("s", "supfildt", _rdate),
    "gstr-1/iff/gstr-1a filing date": ("s", "supfildt", _rdate),
    "isd gstr-6 filing date": ("s", "supfildt", _rdate),
    "invoice details | invoice number": ("i", "inum", None),
    "invoice details | invoice type": ("i", "typ", _rtype),
    "invoice details | invoice date": ("i", "dt", _rdate),
    "invoice details | invoice value": ("i", "val", None),
    "document details | document number": ("i", "inum", None),  # ECO
    "document details | document type": ("i", "typ", _rtype),
    "document details | document date": ("i", "dt", _rdate),
    "document details | document value": ("i", "val", None),
    "credit note/debit note details | note number": ("i", "ntnum", None),
    "credit note/debit note details | note type": ("i", "typ", _rnote),
    "credit note/debit note details | note supply type": ("i", "suptyp", _rtype),
    "credit note/debit note details | note date": ("i", "dt", _rdate),
    "credit note/debit note details | note value": ("i", "val", None),
    "debit note details | note number": ("i", "ntnum", None),  # B2B-DNR (ITC reversal)
    "debit note details | note type": ("i", "typ", _rnote),
    "debit note details | note supply type": ("i", "suptyp", _rtype),
    "debit note details | note date": ("i", "dt", _rdate),
    "debit note details | note value": ("i", "val", None),
    "place of supply": ("i", "pos", _rstate),
    "supply attract reverse charge": ("i", "rev", _ryesno),
    "taxable value": ("i", "txval", None),
    "tax amount | integrated tax": ("i", "igst", None),
    "tax amount | central tax": ("i", "cgst", None),
    "tax amount | state/ut tax": ("i", "sgst", None),
    "tax amount | cess": ("i", "cess", None),
    "itc availability": ("i", "itcavl", _ritc),
    "eligibility of itc": ("i", "itcelg", _ritc),
    "applicable % of tax rate": ("i", "diffprcnt", _rpct),
    "source": ("i", "srctyp", None),
    "irn": ("i", "irn", None),
    "irn date": ("i", "irngendate", _rdate),
    "isd document type": ("i", "doctyp", _risd),
    "isd document number": ("i", "docnum", None),
    "isd document date": ("i", "docdt", _rdate),
    "original invoice number": ("i", "oinvnum", None),
    "original invoice date": ("i", "oinvdt", _rdate),
    "input tax distribution by isd | integrated tax": ("i", "igst", None),
    "input tax distribution by isd | central tax": ("i", "cgst", None),
    "input tax distribution by isd | state/ut tax": ("i", "sgst", None),
    "input tax distribution by isd | cess": ("i", "cess", None),
    "icegate reference date": ("i", "refdt", _rdate),
    "port code": ("i", "portcode", None),
    "bill of entry details | number": ("i", "boenum", None),
    "bill of entry details | date": ("i", "boedt", _rdate),
    "bill of entry details | taxable value": ("i", "txval", None),
    "amount of tax | integrated tax": ("i", "igst", None),
    "amount of tax | cess": ("i", "cess", None),
    "reason": ("i", "rsn", _rreason),
}

RAW_ORIGINAL_2B = {
    "invoice number": ("i", "oinum", None),
    "invoice date": ("i", "oidt", _rdate),
    "note type": ("i", "onttyp", _rnote),
    "note number": ("i", "ontnum", None),
    "note date": ("i", "ontdt", _rdate),
    "isd document type": ("i", "odoctyp", _risd),
    "document number": ("i", "odocnum", None),
    "document date": ("i", "odocdt", _rdate),
}

_ECOA_ORIGINAL_2B = {"document number": ("i", "oinum", None), "document date": ("i", "oidt", _rdate)}

GSTR2B_SHEETS = [
    ("B2B", "docdata", "b2b", "inv", RAW_ORIGINAL_2B),
    ("B2BA", "docdata", "b2ba", "inv", RAW_ORIGINAL_2B),
    ("B2B-CDNR", "docdata", "cdnr", "nt", RAW_ORIGINAL_2B),
    ("B2B-CDNRA", "docdata", "cdnra", "nt", RAW_ORIGINAL_2B),
    ("ISD", "docdata", "isd", "doclist", RAW_ORIGINAL_2B),
    ("ISDA", "docdata", "isda", "doclist", RAW_ORIGINAL_2B),
    ("IMPG", "docdata", "impg", "", RAW_ORIGINAL_2B),
    ("IMPGSEZ", "docdata", "impgsez", "boe", RAW_ORIGINAL_2B),
    ("ECO", "docdata", "ecom", "inv", RAW_ORIGINAL_2B),
    ("ECOA", "docdata", "ecoma", "inv", _ECOA_ORIGINAL_2B),
    ("IMPGA", "docdata", "impga", "", RAW_ORIGINAL_2B),
    ("IMPGSEZA", "docdata", "impgasez", "boe", RAW_ORIGINAL_2B),
    ("B2B (ITC Reversal)", "itcrev", "b2b", "inv", RAW_ORIGINAL_2B),
    ("B2BA (ITC Reversal)", "itcrev", "b2ba", "inv", RAW_ORIGINAL_2B),
    ("B2B-DNR", "itcrev", "cdnr", "nt", RAW_ORIGINAL_2B),
    ("B2B-DNRA", "itcrev", "cdnra", "nt", RAW_ORIGINAL_2B),
    ("B2B(Rejected)", "rejected", "b2b", "inv", RAW_ORIGINAL_2B),
    ("B2BA(Rejected)", "rejected", "b2ba", "inv", RAW_ORIGINAL_2B),
    ("B2B-CDNR(Rejected)", "rejected", "cdnr", "nt", RAW_ORIGINAL_2B),
    ("B2B-CDNRA(Rejected)", "rejected", "cdnra", "nt", RAW_ORIGINAL_2B),
    ("ECO(Rejected)", "rejected", "ecom", "inv", RAW_ORIGINAL_2B),
    ("ECOA(Rejected)", "rejected", "ecoma", "inv", _ECOA_ORIGINAL_2B),
    ("ISD(Rejected)", "rejected", "isd", "doclist", RAW_ORIGINAL_2B),
    ("ISDA(Rejected)", "rejected", "isda", "doclist", RAW_ORIGINAL_2B),
]


_NUMERIC_ZERO_KEYS_2A = {"rt", "txval", "iamt", "camt", "samt", "csamt", "cess"}


RAW_FIELDS_2A = {
    "gstin of supplier": ("s", "ctin", None),
    "gstin of isd": ("s", "ctin", None),
    "gstr-1/iff/gstr-1a/5 filing status": ("s", "cfs", None),
    "gstr-1/iff/gstr-1a/5 filing date": ("s", "fldtr1", None),
    "gstr-1/iff/gstr-1a/5 filing period": ("s", "flprdr1", None),
    "gstr-1/iff/gstr-1a filing status": ("s", "cfs", None),  # ECO variant (no /5)
    "gstr-1/iff/gstr-1a filing date": ("s", "fldtr1", None),
    "gstr-1/iff/gstr-1a filing period": ("s", "flprdr1", None),
    "isd gstr-6 filing status": ("s", "cfs", None),
    "gstr-3b filing status": ("s", "cfs3b", None),
    "effective date of cancellation": ("s", "dtcancel", None),
    "gstin of eco": ("s", "ctin", None),
    "document details | document number": ("i", "inum", None),
    "document details | document type": ("i", "inv_typ", None),
    "document details | document date": ("i", "idt", None),
    "document details | document value": ("i", "val", None),
    "invoice details | invoice number": ("i", "inum", None),
    "invoice details | invoice type": ("i", "inv_typ", None),
    "invoice details | invoice date": ("i", "idt", None),
    "invoice details | invoice value": ("i", "val", None),
    "credit note/debit note details | note type": ("i", "ntty", None),
    "credit note/debit note details | note number": ("i", "nt_num", None),
    "credit note/debit note details | note supply type": ("i", "inv_typ", None),
    "credit note/debit note details | note date": ("i", "nt_dt", None),
    "credit note/debit note details | note value": ("i", "val", None),
    "place of supply": ("i", "pos", _rstate),
    "supply attract reverse charge": ("i", "rchrg", None),
    "tax period in which amended": ("i", "aspd", None),
    "source": ("i", "srctyp", None),
    "irn": ("i", "irn", None),
    "irn date": ("i", "irngendate", None),
    "eligibility of itc": ("i", "itc_elg", None),
    "isd document type": ("i", "isd_docty", None),
    "isd invoice number": ("i", "docnum", None),
    "isd invoice date": ("i", "docdt", None),
    "isd credit note number": ("i", "docnum", None),
    "isd credit note date": ("i", "docdt", None),
    "original invoice number": ("i", "oinvnum", None),
    "original invoice date": ("i", "oinvdt", None),
    "input tax distribution by isd | integrated tax": ("i", "iamt", None),
    "input tax distribution by isd | central tax": ("i", "camt", None),
    "input tax distribution by isd | state/ut tax": ("i", "samt", None),
    "input tax distribution by isd | cess": ("i", "cess", None),
    "reference date (icegate)": ("i", "refdt", None),
    "port code": ("i", "portcd", None),
    "bill of entry details | number": ("i", "benum", None),
    "bill of entry details | date": ("i", "bedt", None),
    "bill of entry details | taxable value": ("i", "txval", None),
    "amount of tax | integrated tax": ("i", "iamt", None),
    "amount of tax | cess": ("i", "csamt", None),
    "amended (yes)": ("i", "amd", None),
    "amended(yes)": ("i", "amd", None),
    "rate": ("it", "rt", None),
    "taxable value": ("it", "txval", None),
    "tax amount | integrated tax": ("it", "iamt", None),
    "tax amount | central tax": ("it", "camt", None),
    "tax amount | state/ut tax": ("it", "samt", None),
    "tax amount | state tax": ("it", "samt", None),
    "tax amount | cess": ("it", "csamt", None),
    "tax amount | cess amount": ("it", "csamt", None),
}

RAW_ORIGINAL_2A = {
    "invoice number": ("i", "oinum", None),
    "invoice date": ("i", "oidt", None),
    "note type": ("i", "ntty", None),
    "note number": ("i", "ont_num", None),
    "note date": ("i", "ont_dt", None),
}
_ECOA_ORIGINAL_2A = {"document number": ("i", "oinum", None), "document date": ("i", "oidt", None)}
ORIGINAL_2A_BY_SECTION = {"ECOA": _ECOA_ORIGINAL_2A}


RAW_FIELDS_2A_TDS = {
    "gstin of deductor": ("i", "gstin_deductor", None),
    "deductor's name": ("i", "deductor_name", None),
    "tax period of gstr 7": ("i", "month", None),  # MMYYYY, as the portal shows it
    "taxable value": ("i", "amt_ded", None),
    "amount of tax deducted by deductors | integrated tax": ("i", "iamt", None),
    "amount of tax deducted by deductors | central tax": ("i", "camt", None),
    "amount of tax deducted by deductors | state/ut tax": ("i", "samt", None),
}

RAW_FIELDS_2A_TCS = {
    "gstin of e-com. operator": ("i", "etin", None),
    "gross value of supplies": ("i", "sup_val", None),
    "net amount liable for tcs": ("i", "tx_val", None),
    "total tcs amount | integrated tax": ("i", "iamt", None),
    "total tcs amount | central tax": ("i", "camt", None),
    "total tcs amount | state/ut tax": ("i", "samt", None),
}

FIELDS_2A_BY_SECTION = {"TDS": RAW_FIELDS_2A_TDS, "TCS": RAW_FIELDS_2A_TCS}

RAW_SECTIONS_2A = {
    "B2B": ("b2b", "inv", "itms"),
    "B2BA": ("b2ba", "inv", "itms"),
    "CDNR": ("cdnr", "nt", "itms"),
    "CDNRA": ("cdnra", "nt", "itms"),
    "ECO": ("eco", "inv", "itms"),
    "ECOA": ("ecoa", "inv", "itms"),
    "ISD": ("isd", "doclist", ""),
    "IMPG": ("impg", "", ""),
    "IMPGSEZ": ("impgsez", "", ""),
    "TDS": ("tds", "", ""),
    "TCS": ("tcs", "", ""),
}


ITC_SHEET_BLOCK = {
    "ITC Available": "itcavl",
    "ITC not available": "itcunavl",
    "ITC Reversal": "itcrev",
    "ITC Rejected": "itcRejected",
}
ITC_TAX_COLUMNS = {"igst": 4, "cgst": 5, "sgst": 6, "cess": 7}


class GovReturnExporter:
    """Render a bundled government template from the stored raw payload, label-driven.
    Subclasses set `return_type` and implement `fill()`; the base handles template
    loading, header-aware cell writing, keeping all sheets, and streaming the file."""

    return_type = None

    def __init__(self, gstin, periods):
        self.gstin = gstin
        self.periods = periods
        self.excel = ExcelExporter(get_data_file_path(TEMPLATES[self.return_type]))
        self.raw = _merged_raw(gstin, self.return_type, periods)

    def build(self):
        filled = self.fill()
        if not filled:
            frappe.throw(frappe._("No data to export for the selected period(s). Sync first, then export."))
        self.fill_readme()
        self._open_on_readme()
        label = self.return_type.replace("GSTR", "GSTR-")
        name = f"{label}-{self.gstin}-{'_'.join(self.periods)}.xlsx"
        return name, self.excel.save_workbook().getvalue()

    def fill(self):
        raise NotImplementedError

    def fill_readme(self):
        """Override to populate the portal's "Read me" header block."""

    def render(self, sheet, build_rows):
        """Read a sheet's header labels, hand them to build_rows(labels) -> list of
        {label: value} dicts, and write those rows. Cells are written directly (not via
        insert_data) so a genuine 0 stays 0 instead of becoming blank."""
        if not self.excel.has_sheet(sheet):
            return False
        ws = self.excel.wb[sheet]
        header_rows, data_start = _header_extent(ws)
        labels = _column_labels(ws, header_rows)
        rows = build_rows(labels)
        for offset, row in enumerate(rows or []):
            for col, label in labels.items():
                value = row.get(label)
                ws.cell(row=data_start + offset, column=col, value="" if value is None else value)
        return bool(rows)

    @staticmethod
    def _records(supplier, list_key):
        """The records under a supplier group: the group's `list_key` list, or the group
        itself for flat sections (IMPG/TDS/TCS) that have no nested list."""
        return (supplier.get(list_key) or []) if list_key else [supplier]

    def _open_on_readme(self):
        # every sheet is kept (empty sections stay blank, like the portal); open on Read me
        if not self.excel.has_sheet("Read me"):
            return
        active = self.excel.wb.sheetnames.index("Read me")
        self.excel.wb.active = active
        for index, worksheet in enumerate(self.excel.wb.worksheets):
            worksheet.sheet_view.tabSelected = index == active

    @staticmethod
    def _live_gstin_name(gstin):
        """Registered (trade/legal) name from the GSTIN registry — for names the payload
        doesn't carry. Guarded so a lookup failure never breaks the export."""
        if not gstin:
            return ""
        try:
            from india_compliance.gst_india.utils.gstin_info import _get_gstin_info

            return (_get_gstin_info(gstin, throw_error=False) or {}).get("business_name") or ""
        except Exception:
            return ""

    @staticmethod
    def _live_gstin_names(gstin):
        """(legal_name, trade_name) from the GSTIN registry, verbatim — for the Read me
        header, which shows the two separately in the portal's casing."""
        if not gstin:
            return "", ""
        try:
            from india_compliance.gst_india.utils.gstin_info import _get_gstin_info

            info = _get_gstin_info(gstin, throw_error=False) or {}
            return info.get("legal_name") or "", info.get("trade_name") or ""
        except Exception:
            return "", ""

    @staticmethod
    def _set_merged(ws, row, col, value):
        """Write to a cell, redirecting to the merge anchor (merged cells are read-only)."""
        for rng in ws.merged_cells.ranges:
            if rng.min_row <= row <= rng.max_row and rng.min_col <= col <= rng.max_col:
                ws.cell(row=rng.min_row, column=rng.min_col, value=value)
                return
        ws.cell(row=row, column=col, value=value)


class GSTR2BExporter(GovReturnExporter):
    """2B: invoice-level document sheets (from docdata / itcrev / docRejdata), codes
    expanded to text, plus the four ITC summary sheets from the portal's itcsumm."""

    return_type = ReturnType.GSTR2B.value

    def fill(self):
        docdata = self.raw.get("docdata", self.raw)
        sources = {
            "docdata": docdata,
            "itcrev": _as_section_dict(docdata.get("itcrev")),
            "rejected": _as_section_dict(self.raw.get("docRejdata")),
        }
        filled = []
        for sheet, source, key, list_key, original in GSTR2B_SHEETS:
            groups = sources[source].get(key) or []
            if groups and self.render(sheet, partial(self._build_rows, groups, list_key, original)):
                filled.append(sheet)

        itcsumm = self._itcsumm()
        for sheet in ITC_SHEET_BLOCK:
            if itcsumm and self.excel.has_sheet(sheet):
                self._fill_itc_sheet(sheet, itcsumm)
                filled.append(sheet)
        return filled

    def _build_rows(self, groups, list_key, original, labels):
        return [
            {label: self._raw_value(label, supplier, record, original) for label in labels.values()}
            for supplier in groups
            for record in self._records(supplier, list_key)
        ]

    @staticmethod
    def _raw_value(label, supplier, record, original=RAW_ORIGINAL_2B):
        """Resolve one 2B cell: the 'original details' block uses the sheet's original
        map, everything else the base map (RAW_FIELDS_2B)."""
        base, is_original = _split_label(label)
        spec = (original if is_original else RAW_FIELDS_2B).get(base)
        if not spec:
            return None
        level, key, transform = spec
        value = (supplier if level == "s" else record).get(key)
        return transform(value) if transform else value

    def fill_readme(self):
        if not self.excel.has_sheet("Read me"):
            return
        period = self.periods[-1]
        legal_name, trade_name = self._live_gstin_names(self.gstin)
        raw = get_raw_return_data(self.gstin, self.return_type, period)

        ws = self.excel.wb["Read me"]
        self._set_merged(ws, 4, 3, _financial_year(period))
        self._set_merged(ws, 5, 3, _reformat_date(period, "%m%Y", "%B"))  # full month name
        self._set_merged(ws, 6, 3, self.gstin)
        self._set_merged(ws, 7, 3, legal_name)  # Legal Name
        self._set_merged(ws, 8, 3, trade_name)  # Trade Name
        self._set_merged(ws, 9, 3, _rdate(raw.get("gendt")) if isinstance(raw, dict) else "")

    def _itcsumm(self):
        """The portal's own computed ITC summary, merged across periods (merge_raw sums
        the numbers). It's part of the stored payload, so we use it directly."""
        merged = {}
        for period in self.periods:
            raw = get_raw_return_data(self.gstin, self.return_type, period)
            if isinstance(raw, dict) and raw.get("itcsumm"):
                merged = merge_raw(merged, raw["itcsumm"])
        return merged

    def _fill_itc_sheet(self, sheet, itcsumm):
        """Label-driven so the four differing layouts all work: section-total rows set
        the current bucket (and get its totals), detail rows get their section's tax
        split. Absent sections are written as 0 (the portal shows 0, not blank)."""
        block = itcsumm.get(ITC_SHEET_BLOCK[sheet]) or {}
        ws = self.excel.wb[sheet]
        bucket = None
        for row in range(1, ws.max_row + 1):
            col_a = _norm(ws.cell(row, 1).value)
            heading = _norm(ws.cell(row, 2).value)
            if not heading or col_a in ("part a", "part b"):
                continue
            if heading.startswith(("b2b", "isd", "eco", "impg")):  # detail row
                if bucket and (key := self._itc_detail_key(heading)):
                    self._write_itc_row(ws, row, (block.get(bucket) or {}).get(key))
            elif new_bucket := self._itc_bucket(heading):  # section-total row
                bucket = new_bucket
                self._write_itc_row(ws, row, block.get(bucket))

    @staticmethod
    def _itc_bucket(label):
        """Section-total row label -> itcsumm bucket key."""
        if "rule 37a" in label or "all other itc" in label:
            return "nonrevsup"
        if "from isd" in label:
            return "isdsup"
        if "reverse charge" in label:
            return "revsup"
        if "import of goods" in label:
            return "imports"
        if label == "others":
            return "othersup"
        return None

    @staticmethod
    def _itc_detail_key(label):
        """Detail row label -> section key within a bucket (amendment = 'a' suffix)."""
        amended = "(amendment)" in label
        if label.startswith("isd"):
            return "isda" if amended else "isd"
        if "impgsez" in label:
            return "impgasez" if amended else "impgsez"
        if "impg" in label:
            return "impga" if amended else "impg"
        if label.startswith("eco"):
            return "ecoma" if amended else "ecom"
        if label.startswith("b2b"):
            if "reverse charge" in label:
                return "cdnrarev" if amended else "cdnrrev"
            if "invoice" in label:
                return "b2ba" if amended else "b2b"
            return "cdnra" if amended else "cdnr"  # debit/credit notes
        return None

    @staticmethod
    def _write_itc_row(ws, row, values):
        for field, col in ITC_TAX_COLUMNS.items():
            ws.cell(row=row, column=col, value=flt((values or {}).get(field)))


class GSTR2AExporter(GovReturnExporter):
    """2A: raw codes shown verbatim, item-level tax with a per-invoice "-Total" row, and
    trade names resolved from GIS / a live GSTIN lookup (the raw doesn't carry them)."""

    return_type = ReturnType.GSTR2A.value

    def fill(self):
        docdata = self.raw.get("docdata", self.raw)
        resolve = self._name_resolver(self._supplier_names())
        period = self.periods[-1]
        filled = []
        for section, sheet in SECTION_SHEETS[self.return_type].items():
            docdata_key, list_key, item_key = RAW_SECTIONS_2A[section]
            groups = docdata.get(docdata_key) or []
            build_rows = partial(self._build_rows, section, groups, list_key, item_key, resolve, period)
            if groups and self.render(sheet, build_rows):
                filled.append(sheet)
        return filled

    def fill_readme(self):
        """Fill the 2A "Read me" header — plain cells C2-C4 / E2-E4 (no merges),
        tax period as MMYYYY."""
        if not self.excel.has_sheet("Read me"):
            return
        period = self.periods[-1]
        legal_name, trade_name = self._live_gstin_names(self.gstin)
        raw = get_raw_return_data(self.gstin, self.return_type, period)
        gendt = raw.get("gendt") if isinstance(raw, dict) else None

        ws = self.excel.wb["Read me"]
        ws.cell(2, 3, self.gstin)  # C2  Taxpayer's GSTIN
        ws.cell(3, 3, legal_name)  # C3  Legal name
        ws.cell(4, 3, trade_name)  # C4  Trade name
        ws.cell(2, 5, period)  # E2  Tax period (MMYYYY)
        ws.cell(3, 5, _financial_year(period))  # E3  Financial year
        ws.cell(4, 5, _rdate(gendt) if gendt else "")  # E4  Date of generation

    def _build_rows(self, section, groups, list_key, item_key, resolve, period, labels):
        fields = FIELDS_2A_BY_SECTION.get(section, RAW_FIELDS_2A)
        original = ORIGINAL_2A_BY_SECTION.get(section, RAW_ORIGINAL_2A)

        def cell(label, supplier, record, item):
            if self._is_trade_name_label(label):
                return supplier.get("trdnm") or resolve(supplier.get("ctin"))
            if label == "e-com. operator's name":
                return resolve(record.get("etin"))
            if label == "tax period of gstr 8":
                return period
            return self._raw_value_2a(label, supplier, record, item, fields, original)

        def row_for(supplier, record, item):
            return {label: cell(label, supplier, record, item) for label in labels.values()}

        rows = []
        for supplier in groups:
            for record in self._records(supplier, list_key):
                if not item_key:
                    rows.append(row_for(supplier, record, {}))
                    continue

                items = [entry.get("itm_det", entry) for entry in record.get(item_key) or []]
                rows.extend(row_for(supplier, record, item) for item in items)
                rows.append(self._total_row(row_for(supplier, record, self._r2a_sum(items)), labels))
                rows.append({})
        return rows

    @staticmethod
    def _total_row(row, labels):
        row["rate"] = "-"
        number_label = next(
            (
                label
                for label in labels.values()
                if label.endswith(("invoice number", "note number", "document number"))
            ),
            None,
        )
        if number_label and row.get(number_label) is not None:
            row[number_label] = f"{row[number_label]}-Total"
        return row

    @staticmethod
    def _raw_value_2a(label, supplier, record, item, fields=RAW_FIELDS_2A, original=RAW_ORIGINAL_2A):
        base, is_original = _split_label(label)
        if base.startswith(("isd invoice", "isd credit note")):
            if (record.get("isd_docty") == "ISDCN") != ("credit note" in base):
                return ""
        if base == "value of supplies returned":
            return round(flt(record.get("sup_val")) - flt(record.get("tx_val")), 2)
        spec = (original if is_original else fields).get(base)
        if not spec:
            return None
        level, key, transform = spec
        value = {"s": supplier, "i": record, "it": item}[level].get(key)
        if value is None and key in _NUMERIC_ZERO_KEYS_2A:
            value = 0
        return transform(value) if transform else value

    @staticmethod
    def _is_trade_name_label(label):
        return _split_label(label)[0].startswith("trade/legal name")

    @staticmethod
    def _r2a_sum(items):
        return {field: sum(flt(it.get(field)) for it in items) for field in _NUMERIC_ZERO_KEYS_2A}

    def _supplier_names(self):
        """{supplier_gstin: supplier_name} resolved during sync — the 2A B2B/CDNR trade
        name isn't in the raw, so it's sourced from GST Inward Supply."""
        GIS = frappe.qb.DocType("GST Inward Supply")
        rows = (
            frappe.qb.from_(GIS)
            .select(GIS.supplier_gstin, GIS.supplier_name)
            .distinct()
            .where(GIS.company_gstin == self.gstin)
            .where(GIS.is_downloaded_from_2a == 1)
            .where(GIS.sup_return_period.isin(self.periods))
            .run(as_dict=True)
        )
        return {row.supplier_gstin: row.supplier_name for row in rows if row.supplier_name}

    @staticmethod
    def _name_resolver(gis_names):
        """Resolve a supplier/operator name: GIS first, then a cached live GSTIN lookup."""
        cache = {}

        def resolve(gstin):
            if not gstin:
                return ""
            if gstin in gis_names:
                return gis_names[gstin]
            if gstin not in cache:
                cache[gstin] = GovReturnExporter._live_gstin_name(gstin)
            return cache[gstin]

        return resolve


EXPORTERS = {
    ReturnType.GSTR2A.value: GSTR2AExporter,
    ReturnType.GSTR2B.value: GSTR2BExporter,
}


def build_export(gstin, return_type, periods):
    """Build the portal-format workbook for the return; returns (file_name, xlsx bytes)."""
    return EXPORTERS[_normalize_return_type(return_type)](gstin, periods).build()


EXPORT_READY_EVENT = "gst_return_export_ready"


def _resolve_periods(company_gstin, return_type, date_range):
    from india_compliance.gst_india.doctype.purchase_reconciliation_tool import BaseUtil

    if isinstance(date_range, str):
        date_range = frappe.parse_json(date_range)
    return BaseUtil.get_periods(date_range, ReturnType(return_type), company_gstin)


def generate_export_file(company_gstin, return_type, date_range, user):
    """Background job: build the workbook, save it as a private File, and notify the
    user (via realtime) with a download link. Errors are reported the same way."""
    try:
        periods = _resolve_periods(company_gstin, return_type, date_range)
        if not periods:
            raise frappe.ValidationError(frappe._("No available periods in the selected range to export."))
        file_name, content = build_export(company_gstin, return_type, periods)
        file = frappe.get_doc(
            {"doctype": "File", "file_name": file_name, "is_private": 1, "content": content}
        ).insert(ignore_permissions=True)
        payload = {"file_url": file.file_url, "file_name": file_name}
    except Exception as exc:
        frappe.db.rollback()
        payload = {"error": str(exc)}
        frappe.log_error(title="GST Return Export failed")

    frappe.publish_realtime(EXPORT_READY_EVENT, payload, user=user)


@frappe.whitelist()
def export_return_as_excel(company_gstin: str, return_type: str, date_range: str | list):
    """Enqueue the export (async); the file download link arrives via realtime."""
    frappe.has_permission("GST Return Export", "export", throw=True)
    return_type = _normalize_return_type(return_type)

    frappe.enqueue(
        generate_export_file,
        queue="long",
        timeout=1500,
        job_id=f"gst_return_export::{company_gstin}::{return_type}",
        deduplicate=True,
        company_gstin=company_gstin,
        return_type=return_type,
        date_range=date_range,
        user=frappe.session.user,
    )
    return {"message": frappe._("Generating your export — the download will start when it's ready.")}
