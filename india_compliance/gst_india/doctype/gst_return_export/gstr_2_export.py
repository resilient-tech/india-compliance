# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

"""
Export GSTR-2A / 2B to the government Excel format, byte-for-byte.

Fills the bundled portal template from the stored raw payload (`docdata`). Columns are
placed by header label read at runtime, not by position. 2B is invoice-level with codes
expanded; 2A is item-level with raw codes and a per-invoice "-Total" row.

Each exporter holds its own template, sheet list and field maps; the module level holds
only the shared header-parsing and value-transform helpers.
"""

import os
import re
import tempfile
from functools import lru_cache, partial
from typing import ClassVar
from zipfile import ZIP_DEFLATED, ZipFile

import frappe
from frappe.query_builder.functions import Max
from frappe.utils import add_days, flt, now_datetime

from india_compliance.gst_india.constants import GST_CATEGORY_MAP, STATE_NUMBERS
from india_compliance.gst_india.doctype.gst_return_log.gst_return_log import (
    get_raw_return_data,
)
from india_compliance.gst_india.utils import (
    get_data_file_path,
    get_periods_between_dates,
    is_production_api_enabled,
    validate_gstin_permission,
)
from india_compliance.gst_india.utils.exporter import ExcelExporter
from india_compliance.gst_india.utils.gstr_2.gstr_2a import map_date_format
from india_compliance.gst_india.utils.gstr_utils import ReturnType
from india_compliance.gst_india.utils.returns_export import merge_raw, normalize_return_type

HEADER_START_ROW = 5

EXCEL_MAX_ROW = 1_048_576

GROUP_BY_MONTHS = {"monthly": 1, "quarterly": 3, "half_yearly": 6, "yearly": 12}
DEFAULT_GROUP_BY = "monthly"

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


def _merge_anchor(ws, row, col):
    """The top-left (row, col) a cell resolves to inside a merged range, or itself if
    unmerged. Merged cells share that anchor for both reads and writes."""
    for rng in ws.merged_cells.ranges:
        if rng.min_row <= row <= rng.max_row and rng.min_col <= col <= rng.max_col:
            return rng.min_row, rng.min_col
    return row, col


def _merged_value(ws, row, col):
    return ws.cell(*_merge_anchor(ws, row, col)).value


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


@lru_cache(maxsize=512)
def _split_label(label):
    """(base_label, is_original) — strip a 'revised details |'/'original details |' prefix.
    Amendment sheets prefix each column so the same field map serves both blocks."""
    if label.startswith(_ORIGINAL):
        return label[len(_ORIGINAL) :], True
    if label.startswith(_REVISED):
        return label[len(_REVISED) :], False
    return label, False


def _as_section_dict(obj):
    """Unwrap a docdata sub-section (itcrev / docRejdata) that may arrive list-wrapped.
    Each period's payload wraps it as a single-element list, so a multi-period merge
    concatenates them; fold every element together instead of taking [0], or all but the
    first period's ITC-reversal documents get silently dropped."""
    if isinstance(obj, list):
        merged = {}
        for item in obj:
            if isinstance(item, dict):
                merged = merge_raw(merged, item)
        return merged
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


def _fy_month_index(period):
    return (int(period[:2]) - 4) % 12


def _group_periods(periods, group_by):
    """Split periods into one list per workbook, on fiscal-year boundaries."""
    months = GROUP_BY_MONTHS.get(group_by) or GROUP_BY_MONTHS[DEFAULT_GROUP_BY]

    groups = {}
    for period in sorted(periods, key=lambda p: (p[2:], p[:2])):
        key = (_financial_year(period), _fy_month_index(period) // months)
        groups.setdefault(key, []).append(period)

    return [groups[key] for key in sorted(groups)]


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


def _ramend(value):  # IMPGA/IMPGSEZA "type of amendment"; A=modify, G/D=new entry
    return {"A": "Amendment", "G": "Addition", "D": "Addition"}.get(value, value or "")


class GovReturnExporter:
    """Render a bundled government template from the stored raw payload, label-driven.
    Subclasses set `return_type` / `template` and their field maps, and implement `fill()`;
    the base handles template loading, header-aware cell writing, keeping all sheets, and
    streaming the file."""

    return_type = None
    template = None
    NUMERIC_ZERO_KEYS = frozenset()

    def __init__(self, gstin, periods):
        if not self.return_type or not self.template:
            raise NotImplementedError(f"{type(self).__name__} must set `return_type` and `template`.")
        self.gstin = gstin
        self.periods = periods
        self.excel = ExcelExporter(get_data_file_path(self.template))
        self.raw = _merged_raw(gstin, self.return_type, periods)

    def build(self):
        """(file_name, xlsx bytes), or None when these period(s) hold no data — a grouped
        export skips the empty groups rather than failing the whole run."""
        if not self.fill():
            return None

        self.fill_readme()
        self._open_on_readme()
        return f"{self.file_stem()}.xlsx", self.excel.save_workbook().getvalue()

    def file_stem(self):
        """`GSTR-2B-<gstin>-<first>_<last>` — first/last rather than every period, so a
        yearly grouping doesn't produce a 90-character file name."""
        label = self.return_type.replace("GSTR", "GSTR-")
        span = self.periods[0] if len(self.periods) == 1 else f"{self.periods[0]}_{self.periods[-1]}"
        return f"{label}-{self.gstin}-{span}"

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
        if not rows:
            return False

        # both sides size themselves off the same capacity, so a length mismatch is a bug
        for target, chunk in zip(
            self._sheets_for(ws, sheet, len(rows), data_start),
            self._chunk(rows, data_start),
            strict=True,
        ):
            for offset, row in enumerate(chunk):
                for col, label in labels.items():
                    value = row.get(label)
                    if value is None or value == "":
                        continue
                    target.cell(row=data_start + offset, column=col, value=value)
        return True

    @staticmethod
    def _chunk(rows, data_start):
        capacity = EXCEL_MAX_ROW - data_start + 1
        if len(rows) <= capacity:
            return [rows]
        return [rows[i : i + capacity] for i in range(0, len(rows), capacity)]

    def _sheets_for(self, ws, sheet, row_count, data_start):
        """[ws] plus a "<sheet> Part N" copy for every chunk past the first.

        The copies are taken while `ws` still holds nothing but the header block, so each one
        arrives with the same merged multi-tier headers, column widths and styling."""
        capacity = EXCEL_MAX_ROW - data_start + 1
        parts = -(-row_count // capacity)

        sheets = [ws]
        for part in range(2, parts + 1):
            copy = self.excel.wb.copy_worksheet(ws)
            copy.title = f"{sheet} Part {part}"[:31]
            sheets.append(copy)
        return sheets

    @staticmethod
    def _records(supplier, list_key):
        """The records under a supplier group: the group's `list_key` list, or the group
        itself for flat sections (IMPG/TDS/TCS) that have no nested list."""
        return (supplier.get(list_key) or []) if list_key else [supplier]

    def _flat_rows(self, groups, list_key, original, fields, labels):
        """One row per record (invoice/document-level). Item-level returns override
        with their own builder."""
        return [
            {
                label: self._raw_value(label, {"s": supplier, "i": record}, fields, original)
                for label in labels.values()
            }
            for supplier in groups
            for record in self._records(supplier, list_key)
        ]

    def _raw_value(self, label, containers, fields, original):
        """Resolve one cell from a field map. The 'original details' block uses the sheet's
        `original` map, everything else `fields`. `containers` maps each level (s/i/it) to
        its source dict. Absent numeric keys listed in NUMERIC_ZERO_KEYS become 0."""
        base, is_original = _split_label(label)
        spec = (original if is_original else fields).get(base)
        if not spec:
            return None
        level, key, transform = spec
        value = containers.get(level, {}).get(key)
        if value is None and key in self.NUMERIC_ZERO_KEYS:
            value = 0
        return transform(value) if transform else value

    def _open_on_readme(self):
        # every sheet is kept (empty sections stay blank, like the portal); open on Read me
        if not self.excel.has_sheet("Read me"):
            return
        active = self.excel.wb.sheetnames.index("Read me")
        self.excel.wb.active = active
        for index, worksheet in enumerate(self.excel.wb.worksheets):
            worksheet.sheet_view.tabSelected = index == active

    @staticmethod
    def _gstin_info(gstin):
        """Legal/trade name for a GSTIN — for the names the payload doesn't carry (company
        name on the Read me header, 2A supplier names)."""
        if not gstin:
            return {}

        cached = frappe.db.get_value("GSTIN", gstin, ("legal_name", "trade_name"), as_dict=True)
        if cached and (cached.legal_name or cached.trade_name):
            return cached

        if not is_production_api_enabled():
            return {}

        try:
            from india_compliance.gst_india.utils.gstin_info import _get_gstin_info

            return _get_gstin_info(gstin, throw_error=False) or {}
        except Exception:
            return {}

    @staticmethod
    def _set_merged(ws, row, col, value):
        """Write to a cell, redirecting to the merge anchor (merged cells are read-only)."""
        row, col = _merge_anchor(ws, row, col)
        ws.cell(row=row, column=col, value=value)


class GSTR2BExporter(GovReturnExporter):
    """2B: invoice-level document sheets (from docdata / itcrev / docRejdata), codes
    expanded to text, plus the four ITC summary sheets from the portal's itcsumm."""

    return_type = ReturnType.GSTR2B.value
    template = "gstr2b_excel_template_v1.0.xlsx"

    RAW_FIELDS: ClassVar[dict] = {
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
        "type of amendment": ("i", "amendType", _ramend),  # IMPGA/IMPGSEZA
        "whether itc to be reduced (taxpayer's input)": ("i", "itcRedReq", _ryesno),
        "amount declared by taxpayer for itc reduction | integrated tax": ("i", "declIgst", None),
        "amount declared by taxpayer for itc reduction | central tax": ("i", "declCgst", None),
        "amount declared by taxpayer for itc reduction | state/ut tax": ("i", "declSgst", None),
        "amount declared by taxpayer for itc reduction | cess": ("i", "declCess", None),
        "remarks": ("i", "remarks", None),
        "taxable value | integrated tax": ("i", "txval", None),
        "taxable value | central tax": ("i", "igst", None),
        "taxable value | state/ut tax": ("i", "cgst", None),
        "taxable value | cess": ("i", "sgst", None),
        "tax amount": ("i", "cess", None),
    }

    RAW_ORIGINAL: ClassVar[dict] = {
        "invoice number": ("i", "oinum", None),
        "invoice date": ("i", "oidt", _rdate),
        "note type": ("i", "onttyp", _rnote),
        "note number": ("i", "ontnum", None),
        "note date": ("i", "ontdt", _rdate),
        "isd document type": ("i", "odoctyp", _risd),
        "document number": ("i", "odocnum", None),
        "document date": ("i", "odocdt", _rdate),
    }

    _ECOA_ORIGINAL: ClassVar[dict] = {
        "document number": ("i", "oinum", None),
        "document date": ("i", "oidt", _rdate),
    }

    SHEETS: ClassVar[list] = [
        ("B2B", "docdata", "b2b", "inv", RAW_ORIGINAL),
        ("B2BA", "docdata", "b2ba", "inv", RAW_ORIGINAL),
        ("B2B-CDNR", "docdata", "cdnr", "nt", RAW_ORIGINAL),
        ("B2B-CDNRA", "docdata", "cdnra", "nt", RAW_ORIGINAL),
        ("ISD", "docdata", "isd", "doclist", RAW_ORIGINAL),
        ("ISDA", "docdata", "isda", "doclist", RAW_ORIGINAL),
        ("ECO", "docdata", "ecom", "inv", RAW_ORIGINAL),
        ("ECOA", "docdata", "ecoma", "inv", _ECOA_ORIGINAL),
        ("B2B (ITC Reversal)", "itcrev", "b2b", "inv", RAW_ORIGINAL),
        ("B2BA (ITC Reversal)", "itcrev", "b2ba", "inv", RAW_ORIGINAL),
        ("B2B-DNR", "itcrev", "cdnr", "nt", RAW_ORIGINAL),
        ("B2B-DNRA", "itcrev", "cdnra", "nt", RAW_ORIGINAL),
        ("B2B(Rejected)", "rejected", "b2b", "inv", RAW_ORIGINAL),
        ("B2BA(Rejected)", "rejected", "b2ba", "inv", RAW_ORIGINAL),
        ("B2B-CDNR(Rejected)", "rejected", "cdnr", "nt", RAW_ORIGINAL),
        ("B2B-CDNRA(Rejected)", "rejected", "cdnra", "nt", RAW_ORIGINAL),
        ("ECO(Rejected)", "rejected", "ecom", "inv", RAW_ORIGINAL),
        ("ECOA(Rejected)", "rejected", "ecoma", "inv", _ECOA_ORIGINAL),
        ("ISD(Rejected)", "rejected", "isd", "doclist", RAW_ORIGINAL),
        ("ISDA(Rejected)", "rejected", "isda", "doclist", RAW_ORIGINAL),
    ]

    ITC_SHEET_BLOCK: ClassVar[dict] = {
        "ITC Available": "itcavl",
        "ITC not available": "itcunavl",
        "ITC Reversal": "itcrev",
        "ITC Rejected": "itcRejected",
    }
    ITC_TAX_COLUMNS: ClassVar[dict] = {"igst": 4, "cgst": 5, "sgst": 6, "cess": 7}

    _ITEM_TAX_KEYS = ("txval", "igst", "cgst", "sgst", "cess")

    def fill(self):
        docdata = self.raw.get("docdata", self.raw)
        sources = {
            "docdata": docdata,
            "itcrev": _as_section_dict(docdata.get("itcrev")),
            "rejected": _as_section_dict(self.raw.get("docRejdata")),
        }
        filled = []
        for sheet, source, key, list_key, original in self.SHEETS:
            groups = sources[source].get(key) or []
            if source == "itcrev":
                groups = self._with_item_totals(groups, list_key)
            build = partial(self._flat_rows, groups, list_key, original, self.RAW_FIELDS)
            if groups and self.render(sheet, build):
                filled.append(sheet)

        self._fill_imports(docdata, filled)

        itcsumm = self.raw.get("itcsumm") or {}
        for sheet in self.ITC_SHEET_BLOCK:
            if itcsumm and self.excel.has_sheet(sheet):
                self._fill_itc_sheet(sheet, itcsumm)
                filled.append(sheet)
        return filled

    def _with_item_totals(self, groups, list_key):
        """ITC-reversal records carry tax only in `items`; sum them to the invoice level so
        the sheet's taxable-value/tax columns fill (these sheets are invoice-level, one row
        per document, like the portal)."""
        result = []
        for group in groups:
            records = []
            for record in group.get(list_key) or []:
                items = record.get("items")
                if items and record.get("txval") is None:
                    totals = {k: sum(flt(it.get(k)) for it in items) for k in self._ITEM_TAX_KEYS}
                    record = {**record, **totals}
                records.append(record)
            result.append({**group, list_key: records})
        return result

    def _fill_imports(self, docdata, filled):
        """IMPG/IMPGSEZ and their amendment sheets are not separate payload sections: the
        payload keeps every bill of entry in `impg`/`impgsez`, and the amended ones
        (isamd == 'Y') belong on IMPGA/IMPGSEZA, the rest on IMPG/IMPGSEZ."""
        plans = [
            ("IMPG", docdata.get("impg"), "", False),
            ("IMPGA", docdata.get("impg"), "", True),
            ("IMPGSEZ", docdata.get("impgsez"), "boe", False),
            ("IMPGSEZA", docdata.get("impgsez"), "boe", True),
        ]
        for sheet, groups, list_key, amended in plans:
            groups = self._imports_by_amendment(groups, list_key, amended)
            build = partial(self._flat_rows, groups, list_key, self.RAW_ORIGINAL, self.RAW_FIELDS)
            if groups and self.render(sheet, build):
                filled.append(sheet)

    @staticmethod
    def _imports_by_amendment(groups, list_key, amended):
        """Keep bill-of-entry records whose amendment state matches. IMPG is flat (records are
        the groups); IMPGSEZ nests them under each supplier's `boe` list."""
        groups = groups or []

        def matches(rec):
            return (rec.get("isamd") == "Y") == amended

        if not list_key:  # flat (IMPG)
            return [rec for rec in groups if matches(rec)]
        filtered = []
        for group in groups:  # grouped (IMPGSEZ)
            boe = [rec for rec in (group.get(list_key) or []) if matches(rec)]
            if boe:
                filtered.append({**group, list_key: boe})
        return filtered

    def fill_readme(self):
        if not self.excel.has_sheet("Read me"):
            return
        period = self.periods[-1]
        info = self._gstin_info(self.gstin)
        gendt = self.raw.get("gendt")

        ws = self.excel.wb["Read me"]
        self._set_merged(ws, 4, 3, _financial_year(period))
        self._set_merged(ws, 5, 3, _reformat_date(period, "%m%Y", "%B"))  # full month name
        self._set_merged(ws, 6, 3, self.gstin)
        self._set_merged(ws, 7, 3, info.get("legal_name") or "")  # Legal Name
        self._set_merged(ws, 8, 3, info.get("trade_name") or "")  # Trade Name
        self._set_merged(ws, 9, 3, _rdate(gendt) if gendt else "")

    def _fill_itc_sheet(self, sheet, itcsumm):
        """Label-driven so the four differing layouts all work: section-total rows set
        the current bucket (and get its totals), detail rows get their section's tax
        split. Absent sections are written as 0 (the portal shows 0, not blank)."""
        block = itcsumm.get(self.ITC_SHEET_BLOCK[sheet]) or {}
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

    def _write_itc_row(self, ws, row, values):
        for field, col in self.ITC_TAX_COLUMNS.items():
            ws.cell(row=row, column=col, value=flt((values or {}).get(field)))


class GSTR2AExporter(GovReturnExporter):
    """2A: raw codes shown verbatim, item-level tax with a per-invoice "-Total" row, and
    trade names resolved from GIS / a live GSTIN lookup (the raw doesn't carry them)."""

    return_type = ReturnType.GSTR2A.value
    template = "gstr2a_excel_template_v1.0.xlsx"

    NUMERIC_ZERO_KEYS: ClassVar[set] = {"rt", "txval", "iamt", "camt", "samt", "csamt", "cess"}

    RAW_FIELDS: ClassVar[dict] = {
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
        "tax period in which amended": ("i", "aspd", None),  # base sheets
        "original tax period in which reported": ("i", "aspd", None),
        "tax period in which reported earlier": ("i", "aspd", None),
        "amendment made, if any": ("i", "atyp", None),
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

    RAW_ORIGINAL: ClassVar[dict] = {
        "invoice number": ("i", "oinum", None),
        "invoice date": ("i", "oidt", None),
        "note type": ("i", "ntty", None),
        "note number": ("i", "ont_num", None),
        "note date": ("i", "ont_dt", None),
    }
    _ECOA_ORIGINAL: ClassVar[dict] = {
        "document number": ("i", "oinum", None),
        "document date": ("i", "oidt", None),
    }
    ORIGINAL_BY_SECTION: ClassVar[dict] = {"ECOA": _ECOA_ORIGINAL}

    RAW_FIELDS_TDS: ClassVar[dict] = {
        "gstin of deductor": ("i", "gstin_deductor", None),
        "deductor's name": ("i", "deductor_name", None),
        "tax period of gstr 7": ("i", "month", None),  # MMYYYY, as the portal shows it
        "taxable value": ("i", "amt_ded", None),
        "amount of tax deducted by deductors | integrated tax": ("i", "iamt", None),
        "amount of tax deducted by deductors | central tax": ("i", "camt", None),
        "amount of tax deducted by deductors | state/ut tax": ("i", "samt", None),
    }

    RAW_FIELDS_TCS: ClassVar[dict] = {
        "gstin of e-com. operator": ("i", "etin", None),
        "gross value of supplies": ("i", "sup_val", None),
        "net amount liable for tcs": ("i", "tx_val", None),
        "total tcs amount | integrated tax": ("i", "iamt", None),
        "total tcs amount | central tax": ("i", "camt", None),
        "total tcs amount | state/ut tax": ("i", "samt", None),
    }

    FIELDS_BY_SECTION: ClassVar[dict] = {"TDS": RAW_FIELDS_TDS, "TCS": RAW_FIELDS_TCS}

    SECTION_SHEETS: ClassVar[dict] = {
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
    }

    RAW_SECTIONS: ClassVar[dict] = {
        "B2B": ("b2b", "inv", "itms"),
        "B2BA": ("b2ba", "inv", "itms"),
        "CDNR": ("cdnr", "nt", "itms"),
        "CDNRA": ("cdnra", "nt", "itms"),
        "ECO": ("ecom", "inv", "itms"),
        "ECOA": ("ecoma", "inv", "itms"),
        "ISD": ("isd", "doclist", ""),
        "IMPG": ("impg", "", ""),
        "IMPGSEZ": ("impgsez", "", ""),
        "TDS": ("tds", "", ""),
        "TCS": ("tcs", "", ""),
    }

    def fill(self):
        docdata = self.raw.get("docdata", self.raw)
        resolve = self._name_resolver(self._supplier_names(), self._registry_names(docdata))
        period = self.periods[-1]
        filled = []
        for section, sheet in self.SECTION_SHEETS.items():
            docdata_key, list_key, item_key = self.RAW_SECTIONS[section]
            groups = docdata.get(docdata_key) or []
            if section == "IMPGSEZ":
                # SEZ imports carry the supplier under sgstin/tdname, not ctin/trdnm
                groups = [{**g, "ctin": g.get("sgstin"), "trdnm": g.get("tdname")} for g in groups]
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
        info = self._gstin_info(self.gstin)
        gendt = self.raw.get("gendt")

        ws = self.excel.wb["Read me"]
        ws.cell(2, 3, self.gstin)  # C2  Taxpayer's GSTIN
        ws.cell(3, 3, info.get("legal_name") or "")  # C3  Legal name
        ws.cell(4, 3, info.get("trade_name") or "")  # C4  Trade name
        ws.cell(2, 5, period)  # E2  Tax period (MMYYYY)
        ws.cell(3, 5, _financial_year(period))  # E3  Financial year
        ws.cell(4, 5, _rdate(gendt) if gendt else "")  # E4  Date of generation

    def _build_rows(self, section, groups, list_key, item_key, resolve, period, labels):
        fields = self.FIELDS_BY_SECTION.get(section, self.RAW_FIELDS)
        original = self.ORIGINAL_BY_SECTION.get(section, self.RAW_ORIGINAL)

        def cell(label, supplier, record, item):
            if self._is_trade_name_label(label):
                return supplier.get("trdnm") or resolve(supplier.get("ctin"))
            if label == "e-com. operator's name":
                return resolve(record.get("etin"))
            if label == "tax period of gstr 8":
                return period
            return self._raw_value(label, {"s": supplier, "i": record, "it": item}, fields, original)

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

    def _raw_value(self, label, containers, fields, original):
        """2A-only computed/conditional cells the (level, key, transform) map can't
        express; everything else falls through to the generic resolver."""
        base, _ = _split_label(label)
        record = containers["i"]
        if base.startswith(("isd invoice", "isd credit note")):
            if (record.get("isd_docty") == "ISDCN") != ("credit note" in base):
                return ""
        if base == "value of supplies returned":
            return round(flt(record.get("sup_val")) - flt(record.get("tx_val")), 2)
        return super()._raw_value(label, containers, fields, original)

    @staticmethod
    def _is_trade_name_label(label):
        return _split_label(label)[0].startswith("trade/legal name")

    @classmethod
    def _r2a_sum(cls, items):
        return {field: sum(flt(it.get(field)) for it in items) for field in cls.NUMERIC_ZERO_KEYS}

    def _supplier_names(self):
        """{supplier_gstin: supplier_name} resolved during sync — the 2A B2B/CDNR trade
        name isn't in the raw, so it's sourced from GST Inward Supply."""
        GIS = frappe.qb.DocType("GST Inward Supply")
        rows = (
            frappe.qb.from_(GIS)
            .select(GIS.supplier_gstin, Max(GIS.supplier_name).as_("supplier_name"))
            .where(GIS.company_gstin == self.gstin)
            .where(GIS.is_downloaded_from_2a == 1)
            .where(GIS.sup_return_period.isin(self.periods))
            .groupby(GIS.supplier_gstin)
            .run(as_dict=True)
        )
        return {row.supplier_gstin: row.supplier_name for row in rows if row.supplier_name}

    def _registry_names(self, docdata):
        """{gstin: legal_name} for every supplier in the payload, in one query per 5k GSTINs."""
        gstins = {
            group.get("ctin") or group.get("sgstin")
            for section in self.RAW_SECTIONS.values()
            for group in (docdata.get(section[0]) or [])
            if isinstance(group, dict)
        }
        gstins.discard(None)
        if not gstins:
            return {}

        gstins = list(gstins)
        names = {}
        for start in range(0, len(gstins), 5000):
            names.update(
                {
                    row.name: row.legal_name
                    for row in frappe.get_all(
                        "GSTIN",
                        filters={"name": ("in", gstins[start : start + 5000])},
                        fields=["name", "legal_name"],
                    )
                    if row.legal_name
                }
            )
        return names

    @staticmethod
    def _name_resolver(gis_names, registry_names=None):
        """Resolve a supplier/operator name. The 2A raw doesn't carry it and the portal shows
        the registered legal name, so prefer the registry legal name, then the name synced to
        GIS, then the business name.

        `registry_names` is the batched pre-resolve; anything it misses (an operator `etin`, a
        GSTIN we've never looked up) falls through to one lookup per unique GSTIN."""
        cache = dict(registry_names or {})

        def resolve(gstin):
            if not gstin:
                return ""
            if gstin not in cache:
                info = GovReturnExporter._gstin_info(gstin)
                cache[gstin] = (
                    info.get("legal_name") or gis_names.get(gstin) or info.get("business_name") or ""
                )
            return cache[gstin]

        return resolve


EXPORTERS = {
    ReturnType.GSTR2A.value: GSTR2AExporter,
    ReturnType.GSTR2B.value: GSTR2BExporter,
}


def build_export(gstin, return_type, periods, group_by=DEFAULT_GROUP_BY):
    """Build the portal-format export; returns (file_name, bytes)."""
    exporter = EXPORTERS.get(normalize_return_type(return_type))
    if not exporter:
        frappe.throw(frappe._("Export is not supported for {0}").format(return_type))

    groups = _group_periods(periods, group_by)
    if len(groups) == 1:
        built = exporter(gstin, groups[0]).build()
        if not built:
            _throw_no_data()
        return built

    fd, zip_path = tempfile.mkstemp(suffix=".zip")
    os.close(fd)
    try:
        written = 0
        with ZipFile(zip_path, "w", ZIP_DEFLATED) as archive:
            for group in groups:
                if built := exporter(gstin, group).build():
                    archive.writestr(*built)
                    written += 1

        if not written:
            _throw_no_data()

        with open(zip_path, "rb") as f:
            content = f.read()
    finally:
        os.remove(zip_path)

    label = normalize_return_type(return_type).replace("GSTR", "GSTR-")
    return f"{label}-{gstin}-{periods[0]}_{periods[-1]}.zip", content


def _throw_no_data():
    frappe.throw(frappe._("No data to export for the selected period(s). Sync first, then export."))


EXPORT_READY_EVENT = "gst_return_export_ready"
DOCTYPE = "GST Return Export"


def generate_export_file(company_gstin, return_type, from_date, to_date, user, group_by=DEFAULT_GROUP_BY):
    """Background job: build the export, save it as a private File attached to the tool, and
    notify the user (via realtime) with the File id to download. Errors are reported the same
    way."""
    try:
        periods = get_periods_between_dates(from_date, to_date)
        if not periods:
            raise frappe.ValidationError(frappe._("No available periods in the selected range to export."))
        file_name, content = build_export(company_gstin, return_type, periods, group_by)
        file = frappe.get_doc(
            {
                "doctype": "File",
                "file_name": file_name,
                "attached_to_doctype": DOCTYPE,
                "attached_to_name": DOCTYPE,
                "is_private": 1,
                "content": content,
            }
        ).insert(ignore_permissions=True)
        payload = {"file_id": file.name, "file_name": file_name}
    except Exception as exc:
        frappe.db.rollback()
        payload = {"error": str(exc)}
        frappe.log_error(title="GST Return Export failed")

    frappe.publish_realtime(EXPORT_READY_EVENT, payload, user=user)


@frappe.whitelist()
def download_export_file(file_id: str):
    """Stream a generated export to the browser, straight off disk (no full-file copy in
    memory). Guarded by the same `export` permission as producing it, and restricted to files
    this tool created — so it can't be used to fetch arbitrary private Files. The file itself
    is reaped later by `delete_stale_export_files` (a streamed response can't safely unlink
    mid-send)."""
    frappe.has_permission(DOCTYPE, "export", throw=True)

    file = frappe.get_doc("File", file_id)
    if file.attached_to_doctype != DOCTYPE or file.owner != frappe.session.user:
        frappe.throw(frappe._("This file is not a GST Return Export."), frappe.PermissionError)

    from frappe.utils.response import send_private_file

    return send_private_file(file.file_url.split("/private", 1)[1], filename=file.file_name)


def delete_stale_export_files():
    """Daily: drop generated exports older than a day. These are download-once artifacts, so
    without this every Export click leaks a multi-MB private File. Drained in batches so a
    day's backlog can't outrun a single fixed cap."""
    while True:
        stale = frappe.get_all(
            "File",
            filters={
                "attached_to_doctype": DOCTYPE,
                "creation": ("<", add_days(now_datetime(), -1)),
            },
            pluck="name",
            limit=500,
            order_by="creation asc",
        )
        if not stale:
            return
        for name in stale:
            frappe.delete_doc("File", name, ignore_permissions=True, delete_permanently=True)
        frappe.db.commit()


@frappe.whitelist()
@validate_gstin_permission(doctype=DOCTYPE)
def export_return_as_excel(
    company_gstin: str,
    return_type: str,
    from_date: str,
    to_date: str,
    group_by: str = DEFAULT_GROUP_BY,
):
    """Enqueue the export (async); the download is triggered via realtime when ready."""
    frappe.has_permission(DOCTYPE, "export", throw=True)
    return_type = normalize_return_type(return_type)
    if group_by not in GROUP_BY_MONTHS:
        group_by = DEFAULT_GROUP_BY

    frappe.enqueue(
        generate_export_file,
        queue="long",
        timeout=1500,
        job_id=f"gst_return_export:{company_gstin}:{return_type}:{from_date}:{to_date}:{group_by}",
        deduplicate=True,
        company_gstin=company_gstin,
        return_type=return_type,
        from_date=from_date,
        to_date=to_date,
        group_by=group_by,
        user=frappe.session.user,
    )
    return {"message": frappe._("Generating your export — the download will start when it's ready.")}
