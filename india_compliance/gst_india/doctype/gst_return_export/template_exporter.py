# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

"""Fill a bundled portal template from stored raw. Knows no specific return."""

import re
from datetime import datetime
from functools import lru_cache
from typing import ClassVar

import frappe
from frappe.utils import flt

from india_compliance.gst_india.constants import STATE_NUMBERS
from india_compliance.gst_india.doctype.gst_return_log.gst_return_log import (
    get_raw_return_data,
)
from india_compliance.gst_india.utils import get_data_file_path
from india_compliance.gst_india.utils.exporter import ExcelExporter

HEADER_START_ROW = 5

EXCEL_MAX_ROW = 1_048_576

GROUP_BY_MONTHS = {"monthly": 1, "quarterly": 3, "half_yearly": 6, "yearly": 12}
GROUP_BY_ALL = "all"
DEFAULT_GROUP_BY = "monthly"

_REVISED = "revised details | "
_ORIGINAL = "original details | "
_WS = re.compile(r"\s+")


# ---- template headers -> column labels


def normalize_label(value):
    """Header text made comparable."""
    if value is None:
        return ""
    value = re.sub(r"\(₹\)|\(%\)|₹", "", str(value))
    return _WS.sub(" ", value).strip().lower()


def merged_top_left(ws, row, col):
    """A merged cell is read and written at its top-left corner."""
    for rng in ws.merged_cells.ranges:
        if rng.min_row <= row <= rng.max_row and rng.min_col <= col <= rng.max_col:
            return rng.min_row, rng.min_col
    return row, col


def merged_value(ws, row, col):
    return ws.cell(*merged_top_left(ws, row, col)).value


def header_extent(ws):
    """Headers = row 5 down to first empty row."""
    row = HEADER_START_ROW
    while row <= ws.max_row:
        if all(merged_value(ws, row, c) in (None, "") for c in range(1, ws.max_column + 1)):
            break
        row += 1
    return list(range(HEADER_START_ROW, row)), row


def column_labels(ws, header_rows):
    """Column -> its full header label."""
    labels = {}
    for col in range(1, ws.max_column + 1):
        parts = []
        for r in header_rows:
            value = normalize_label(merged_value(ws, r, col))
            if value and (not parts or parts[-1] != value):
                parts.append(value)
        labels[col] = " | ".join(parts)
    return labels


@lru_cache(maxsize=512)
def split_label(label):
    """Strip revised/original prefix so one map serve both blocks."""
    if label.startswith(_ORIGINAL):
        return label[len(_ORIGINAL) :], True
    if label.startswith(_REVISED):
        return label[len(_REVISED) :], False
    return label, False


# ---- stored raw data


def merge_raw(existing, new):
    """Merge months' raw data: lists join, numbers add, null never wins."""
    if isinstance(existing, dict) and isinstance(new, dict):
        merged = dict(existing)
        for key, value in new.items():
            merged[key] = merge_raw(merged[key], value) if key in merged else value
        return merged

    if isinstance(existing, list) and isinstance(new, list):
        return existing + new

    if isinstance(existing, (int, float)) and isinstance(new, (int, float)):
        return existing + new

    return existing if new is None else new


def as_section_dict(obj):
    """Portal wraps this block in a list. Fold every element."""
    if isinstance(obj, list):
        merged = {}
        for item in obj:
            if isinstance(item, dict):
                merged = merge_raw(merged, item)
        return merged
    return obj or {}


# ---- formatters: stored or raw value -> what the portal cell shows


def reformat_date(value, source_format, target_format):
    """Change date text format. Bad value pass through."""
    try:
        return datetime.strptime(value, source_format).strftime(target_format) if value else ""
    except (ValueError, TypeError):
        return value or ""


def date_text(value):  # date -> "21/05/2026"
    return value.strftime("%d/%m/%Y")


def raw_date_text(value):  # "DD-MM-YYYY" -> "DD/MM/YYYY"
    return reformat_date(value, "%d-%m-%Y", "%d/%m/%Y")


def period_text(value):  # "042026" -> "Apr'26"
    return reformat_date(value, "%m%Y", "%b'%y")


_NUMBER_TO_STATE = {number: name for name, number in STATE_NUMBERS.items()}


def state_text(value):  # "24-Gujarat" -> "Gujarat"
    return str(value).split("-", 1)[-1]


def state_from_code(value):  # "24" -> "Gujarat" (2A keeps the bare state code)
    return _NUMBER_TO_STATE.get(str(value).zfill(2), value)


def yes_no_text(value):  # stored check -> the portal's word
    return {1: "Yes", 0: "No"}.get(value, "")


def raw_yes_no_text(value):
    return {"Y": "Yes", "N": "No"}.get(value, "")


def percent_text(value):  # 0.65 -> "65%"
    return f"{flt(value) * 100:g}%"


def amend_text(value):  # IMPGA/IMPGSEZA "type of amendment"; A=modify, G/D=new entry
    return {"A": "Amendment", "G": "Addition", "D": "Addition"}.get(value, value or "")


def financial_year(period):  # "MMYYYY" -> "2019-20" (Indian FY starts in April)
    month, year = int(period[:2]), int(period[2:])
    start = year if month >= 4 else year - 1
    return f"{start}-{str(start + 1)[-2:]}"


# ---- periods and file names


def group_periods(periods, group_by):
    """Periods -> one list per workbook, never across a fiscal year."""
    periods = sorted(periods, key=lambda p: (p[2:], p[:2]))
    if group_by == GROUP_BY_ALL:
        return [periods]

    months = GROUP_BY_MONTHS[group_by]
    groups = {}
    for period in periods:
        fy_month = (int(period[:2]) - 4) % 12
        groups.setdefault((financial_year(period), fy_month // months), []).append(period)
    return [groups[key] for key in sorted(groups)]


def return_label(return_type):  # "GSTR2b" -> "GSTR-2B"
    return return_type.upper().replace("GSTR", "GSTR-")


def workbook_name(return_type, gstin, periods):
    """GSTR-2B-<gstin>-<first>[_<last>].xlsx"""
    span = periods[0] if len(periods) == 1 else f"{periods[0]}_{periods[-1]}"
    return f"{return_label(return_type)}-{gstin}-{span}.xlsx"


# ---- cells


def spec_value(spec, source, exporter=None):
    """Cell value from one map entry: key, (key, formatter), or computed(source, exporter)."""
    if not spec:
        return None
    if callable(spec):
        return spec(source, exporter)
    field, formatter = spec if isinstance(spec, tuple) else (spec, None)
    value = source.get(field)
    if value is None or value == "":
        return None
    return formatter(value) if formatter else value


def write_cell(ws, row, col, value):
    """Text stays text: a value starting with "=" must not turn into a formula."""
    cell = ws.cell(row=row, column=col, value=value)
    if isinstance(value, str) and cell.data_type == "f":
        cell.data_type = "s"
    return cell


class GovReturnExporter:
    """Base exporter. Subclass set adapter/template/maps and fill()."""

    adapter = None
    template = None
    # portal number format for numeric cells
    NUMBER_FORMAT = None

    # Column maps. A header label resolves in this order:
    #   SHEET_FIELDS[sheet][full label]      one sheet's special cases, keyed as the header reads
    #   ORIGINAL_FIELDS[base]                "original details | ..." columns
    #   FIELDS[base]                         everything else; "revised details | " is stripped
    # A spec is a source key, (key, formatter), or computed(source, exporter). None = unmapped.
    FIELDS: ClassVar[dict] = {}
    ORIGINAL_FIELDS: ClassVar[dict] = {}
    SHEET_FIELDS: ClassVar[dict] = {}

    def __init__(self, gstin, periods):
        self.gstin = gstin
        self.periods = periods
        self.return_type = self.adapter.return_type
        self.excel = ExcelExporter(get_data_file_path(self.template))

        self.raw_by_period = {}
        self.raw = {}
        for period in periods:
            raw = get_raw_return_data(gstin, self.return_type, period)
            if isinstance(raw, dict):
                self.raw_by_period[period] = raw
                self.raw = merge_raw(self.raw, raw)

    def build(self):
        """(file_name, bytes); None when no data so grouped runs skip, not fail."""
        if not self.fill():
            return None
        self.fill_readme()

        # open on Read me; empty sheets stay, like the portal
        if self.excel.has_sheet("Read me"):
            active = self.excel.wb.sheetnames.index("Read me")
            self.excel.wb.active = active
            for index, worksheet in enumerate(self.excel.wb.worksheets):
                worksheet.sheet_view.tabSelected = index == active

        name = workbook_name(self.return_type, self.gstin, self.periods)
        return name, self.excel.save_workbook().getvalue()

    def fill(self):
        raise NotImplementedError

    def fill_readme(self):
        """Read me header. Per return."""

    def render(self, sheet, build_rows):
        """Write rows under the headers. Direct writes keep 0 as 0."""
        if not self.excel.has_sheet(sheet):
            return False

        # headers
        ws = self.excel.wb[sheet]
        header_rows, data_start = header_extent(ws)
        labels = column_labels(ws, header_rows)

        # rows
        rows = build_rows(labels)
        if not rows:
            return False

        # write, spilling onto Part sheets past Excel's row cap
        capacity = EXCEL_MAX_ROW - data_start + 1
        chunks = [rows[i : i + capacity] for i in range(0, len(rows), capacity)]
        for target, chunk in zip(self._sheets_for(ws, sheet, len(chunks)), chunks, strict=True):
            for offset, row in enumerate(chunk):
                for col, label in labels.items():
                    value = row.get(label)
                    if value is None or value == "":
                        continue
                    cell = write_cell(target, data_start + offset, col, value)
                    if self.NUMBER_FORMAT and isinstance(value, (int, float)):
                        cell.number_format = self.NUMBER_FORMAT
        return True

    def _sheets_for(self, ws, sheet, count):
        """Sheet plus "Part N" copies when rows overflow Excel. Copy before any write."""
        sheets = [ws]
        for part in range(2, count + 1):
            copy = self.excel.wb.copy_worksheet(ws)
            copy.title = f"{sheet} Part {part}"[:31]
            sheets.append(copy)
        return sheets

    def rows_for(self, sheet, labels, sources):
        """One workbook row per source dict (None = blank row), specs resolved once per sheet."""
        specs = {label: self.spec_for(label, sheet) for label in labels.values()}
        return [
            {} if source is None else {label: spec_value(spec, source, self) for label, spec in specs.items()}
            for source in sources
        ]

    @classmethod
    def spec_for(cls, label, sheet=None):
        """One column's spec, or None when nothing fills it."""
        overrides = cls.SHEET_FIELDS.get(sheet) or {}
        if label in overrides:
            return overrides[label]
        base, is_original = split_label(label)
        return (cls.ORIGINAL_FIELDS if is_original else cls.FIELDS).get(base)

    # ---- for subclass fill_readme

    @staticmethod
    def get_gstin_names(gstin):
        """Names off the cached GSTIN row. Never a live lookup."""
        if not gstin:
            return {}
        return frappe.db.get_value("GSTIN", gstin, ("legal_name", "trade_name"), as_dict=True) or {}

    @staticmethod
    def set_merged(ws, row, col, value):
        """Merged cells only writable at their top-left corner."""
        row, col = merged_top_left(ws, row, col)
        write_cell(ws, row, col, value)
