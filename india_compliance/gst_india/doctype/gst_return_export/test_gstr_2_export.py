# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

"""2A/2B exporters: cell checks, golden workbooks in gst_india/data, delivery lifecycle."""

from contextlib import ExitStack, contextmanager
from io import BytesIO
from typing import ClassVar
from unittest.mock import Mock, patch
from zipfile import ZipFile

import frappe
import openpyxl
from frappe import parse_json, read_file
from frappe.core.doctype.file.utils import delete_file
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, now_datetime

from india_compliance.gst_india.doctype.gst_return_export.gst_return_export import (
    DOCTYPE,
    RETURN_LOG,
    build_export,
    delete_stale_export_files,
    download_export_file,
    export_file_name,
    export_key,
    generate_export_file,
    get_reusable_export,
)
from india_compliance.gst_india.doctype.gst_return_export.gstr_2_export import (
    GSTR2AExporter,
    GSTR2BExporter,
)
from india_compliance.gst_india.doctype.gst_return_export.template_exporter import (
    GovReturnExporter,
    group_periods,
)
from india_compliance.gst_india.doctype.gst_return_log.gst_return_log import (
    store_raw_return_data,
)
from india_compliance.gst_india.utils import get_data_file_path
from india_compliance.gst_india.utils.gstr_utils import ReturnType

ENGINE_MODULE = "india_compliance.gst_india.doctype.gst_return_export.template_exporter"

GSTIN_2B = "01AABCE2207R1Z5"
PERIOD_2B = "032020"
GOLDEN_2B = "test_gstr2b_export_golden.xlsx"

GSTIN_2A = "24AACT1234F1Z5"
PERIOD_2A = "052024"
GOLDEN_2A = "test_gstr2a_export_golden.xlsx"

MOCK_LEGAL = "LEGAL NAME"
MOCK_TRADE = "TRADE NAME"
MOCK_BUSINESS = "GSTN"

RAW_2A = {
    "b2b": [
        {
            "ctin": GSTIN_2A,
            "trdnm": "Acme Traders",
            "inv": [
                {
                    "inum": "INV-001",
                    "idt": "10-05-2024",
                    "val": 14200,
                    "pos": "06",
                    "itms": [
                        {"itm_det": {"rt": 18, "txval": 10000, "iamt": 0, "camt": 900, "samt": 900}},
                        {"itm_det": {"rt": 5, "txval": 2000, "iamt": 100}},
                    ],
                }
            ],
        }
    ],
    "isd": [
        {
            "ctin": "16DEFPS8555D1Z7",
            "trdnm": "ISD Co",
            "doclist": [
                {
                    "isd_docty": "ISD",
                    "docnum": "S0080",
                    "docdt": "03-03-2016",
                    "iamt": 20,
                    "camt": 20,
                    "samt": 20,
                },
                {
                    "isd_docty": "ISDCN",
                    "docnum": "CN-1",
                    "docdt": "04-03-2016",
                    "iamt": 5,
                    "camt": 5,
                    "samt": 5,
                },
            ],
        }
    ],
    "tcs": [{"etin": "27AAECS1234F1Z5", "sup_val": 1000, "tx_val": 900, "iamt": 10, "camt": 5, "samt": 5}],
}


def _load(content):
    return openpyxl.load_workbook(BytesIO(content))


def _cells(ws):
    """Every non-empty cell of a sheet."""
    return {
        (cell.row, cell.column): cell.value
        for row in ws.iter_rows()
        for cell in row
        if cell.value not in (None, "")
    }


def _data_row_count(ws, start=7, col=1):
    """Data rows below the header block."""
    return sum(1 for r in range(start, ws.max_row + 1) if ws.cell(r, col).value not in (None, ""))


@contextmanager
def _mock_names(raw):
    """Feed raw and fixed names."""
    with ExitStack() as stack:
        stack.enter_context(patch(f"{ENGINE_MODULE}.get_raw_return_data", return_value=raw))
        stack.enter_context(
            patch.object(
                GovReturnExporter,
                "get_gstin_names",
                staticmethod(
                    lambda gstin: {
                        "business_name": MOCK_BUSINESS,
                        "legal_name": MOCK_LEGAL,
                        "trade_name": MOCK_TRADE,
                    }
                ),
            )
        )
        yield stack


def _remove_file_later(test, file):
    """Rollback drops the row, not the disk copy."""

    def remove():
        if frappe.db.exists("File", file.name):
            frappe.delete_doc("File", file.name, ignore_permissions=True, delete_permanently=True)
        else:
            delete_file(file.file_url)

    test.addCleanup(remove)


def _build_periods(exporter_cls, gstin, periods, raw, supplier_names=None):
    """Build; (file_name, workbook). Same raw per period, so two periods test the merge."""
    with _mock_names(raw) as stack:
        if supplier_names is not None:
            stack.enter_context(
                patch.object(GSTR2AExporter, "_supplier_names", lambda self, gstins: supplier_names)
            )
        name, content = exporter_cls(gstin, periods).build()
    return name, _load(content)


def _build(exporter_cls, gstin, period, raw, supplier_names=None):
    """One period; workbook only."""
    return _build_periods(exporter_cls, gstin, [period], raw, supplier_names)[1]


class TestGSTR2BExport(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.raw = parse_json(read_file(get_data_file_path("test_gstr_2b_v4_0.json")))["data"]
        cls.wb = _build(GSTR2BExporter, GSTIN_2B, PERIOD_2B, cls.raw)

    def test_b2b_row_values(self):
        """Invoice-level row: codes expanded, dates DD/MM/YYYY, period Mon'YY, 0 stays 0."""
        ws = self.wb["B2B"]
        self.assertEqual(ws.cell(7, 1).value, GSTIN_2B)
        self.assertEqual(ws.cell(7, 2).value, "GSTN")
        self.assertEqual(ws.cell(7, 3).value, "S008400")
        self.assertEqual(ws.cell(7, 4).value, "Regular")
        self.assertEqual(ws.cell(7, 5).value, "24/11/2016")
        self.assertEqual(ws.cell(7, 6).value, 729248.16)
        self.assertEqual(ws.cell(7, 7).value, "Haryana")
        self.assertEqual(ws.cell(7, 8).value, "No")
        self.assertEqual(ws.cell(7, 9).value, 12200)
        self.assertEqual(ws.cell(7, 10).value, 183)
        self.assertEqual(ws.cell(7, 11).value, 0)
        self.assertEqual(ws.cell(7, 14).value, "Nov'19")
        self.assertEqual(ws.cell(7, 18).value, "100%")

    def test_itc_available_summary(self):
        """ITC summary from the portal's itcsumm: a section-total row then its detail rows."""
        ws = self.wb["ITC Available"]
        self.assertEqual([ws.cell(9, c).value for c in (4, 5, 6, 7)], [1600, 800, 800, 400])
        self.assertEqual([ws.cell(10, c).value for c in (4, 5, 6, 7)], [400, 200, 200, 100])

    def test_readme_header(self):
        ws = self.wb["Read me"]
        self.assertEqual(ws.cell(4, 3).value, "2019-20")
        self.assertEqual(ws.cell(5, 3).value, "March")
        self.assertEqual(ws.cell(6, 3).value, GSTIN_2B)
        self.assertEqual(ws.cell(7, 3).value, MOCK_LEGAL)
        self.assertEqual(ws.cell(8, 3).value, MOCK_TRADE)
        self.assertEqual(ws.cell(9, 3).value, "14/04/2020")

    def test_all_template_sheets_retained(self):
        self.assertIn("ISDA", self.wb.sheetnames)
        self.assertIn("ECOA(Rejected)", self.wb.sheetnames)

    def test_matches_golden_workbook(self):
        """Every sheet's cell values match the committed golden (values, not bytes)."""
        golden = openpyxl.load_workbook(get_data_file_path(GOLDEN_2B))
        self.assertEqual(self.wb.sheetnames, golden.sheetnames)
        for sheet in golden.sheetnames:
            self.assertEqual(
                _cells(self.wb[sheet]), _cells(golden[sheet]), msg=f"cell mismatch in sheet {sheet!r}"
            )

    def test_multi_period_merges_and_names_file(self):
        """Two periods: sections join, itcsumm adds, Read me shows the last, name joins both."""
        single_b2b = _data_row_count(self.wb["B2B"])
        single_revb2b = _data_row_count(self.wb["B2B (ITC Reversal)"])
        single_nonrevsup = self.wb["ITC Available"].cell(9, 4).value

        name, wb = _build_periods(GSTR2BExporter, GSTIN_2B, [PERIOD_2B, "042020"], self.raw)

        self.assertEqual(_data_row_count(wb["B2B"]), 2 * single_b2b)
        # itcrev arrives list-wrapped; both periods' reversal docs must survive the merge
        self.assertEqual(_data_row_count(wb["B2B (ITC Reversal)"]), 2 * single_revb2b)
        self.assertEqual(wb["ITC Available"].cell(9, 4).value, 2 * single_nonrevsup)
        self.assertEqual(wb["Read me"].cell(5, 3).value, "April")
        self.assertEqual(wb["Read me"].cell(4, 3).value, "2020-21")
        self.assertIn(f"{PERIOD_2B}_042020", name)

    def test_import_amendment_split(self):
        """isamd splits IMPG from IMPGA; the payload has no impga section."""
        raw = {
            "docdata": {
                "impg": [
                    {"boenum": "BE-ORIG", "isamd": "N", "txval": 100, "igst": 18, "cess": 0},
                    {"boenum": "BE-AMD", "isamd": "Y", "amendType": "A", "txval": 200, "igst": 36, "cess": 0},
                ]
            }
        }
        wb = _build(GSTR2BExporter, GSTIN_2B, PERIOD_2B, raw)
        impg, impga = wb["IMPG"], wb["IMPGA"]
        self.assertEqual(impg.cell(7, 3).value, "BE-ORIG")
        self.assertIsNone(impg.cell(8, 3).value)  # amended row is not in IMPG
        self.assertEqual(impga.cell(7, 3).value, "BE-AMD")
        self.assertEqual(impga.cell(7, 6).value, 36)  # amount of tax | integrated
        self.assertEqual(impga.cell(7, 8).value, "Amendment")  # type of amendment (A)

    def test_impgsez_amendment_split(self):
        """SEZ bills of entry are nested under a supplier; split each supplier's boe list."""
        raw = {
            "docdata": {
                "impgsez": [
                    {
                        "ctin": "29ABCDE1234F1Z5",
                        "trdnm": "SEZ Co",
                        "boe": [
                            {"boenum": "S-ORIG", "isamd": "N", "txval": 10, "igst": 2},
                            {"boenum": "S-AMD", "isamd": "Y", "amendType": "G", "txval": 20, "igst": 4},
                        ],
                    }
                ]
            }
        }
        wb = _build(GSTR2BExporter, GSTIN_2B, PERIOD_2B, raw)
        self.assertEqual(wb["IMPGSEZ"].cell(7, 1).value, "29ABCDE1234F1Z5")
        self.assertEqual(wb["IMPGSEZ"].cell(7, 5).value, "S-ORIG")
        self.assertEqual(wb["IMPGSEZA"].cell(7, 5).value, "S-AMD")
        self.assertEqual(wb["IMPGSEZA"].cell(7, 10).value, "Addition")  # type of amendment (G)

    def test_itc_reversal_sums_items(self):
        """Reversal invoices carry tax only in items; the sheet shows the sum, one row per document."""
        raw = {
            "docdata": {
                "itcrev": {
                    "b2b": [
                        {
                            "ctin": GSTIN_2B,
                            "trdnm": "X",
                            "inv": [
                                {
                                    "inum": "REV-1",
                                    "items": [
                                        {"txval": 100, "igst": 18, "cgst": 0, "sgst": 0, "cess": 0},
                                        {"txval": 50, "igst": 9, "cgst": 0, "sgst": 0, "cess": 0},
                                    ],
                                }
                            ],
                        }
                    ]
                }
            }
        }
        ws = _build(GSTR2BExporter, GSTIN_2B, PERIOD_2B, raw)["B2B (ITC Reversal)"]
        self.assertEqual(ws.cell(7, 3).value, "REV-1")
        self.assertEqual(ws.cell(7, 9).value, 150)  # taxable value (summed)
        self.assertEqual(ws.cell(7, 10).value, 27)  # integrated tax (18 + 9)

    def test_itc_reduction_and_remarks_columns(self):
        raw = {
            "docdata": {
                "b2ba": [
                    {
                        "ctin": GSTIN_2B,
                        "trdnm": "X",
                        "inv": [
                            {
                                "inum": "A-1",
                                "oinum": "O-1",
                                "itcRedReq": "Y",
                                "declIgst": 5,
                                "declCgst": 2,
                                "declSgst": 2,
                                "declCess": 1,
                                "remarks": "note",
                            }
                        ],
                    }
                ]
            }
        }
        ws = _build(GSTR2BExporter, GSTIN_2B, PERIOD_2B, raw)["B2BA"]
        self.assertEqual(ws.cell(8, 16).value, "Yes")  # whether itc to be reduced
        self.assertEqual([ws.cell(8, c).value for c in (17, 18, 19, 20)], [5, 2, 2, 1])
        self.assertEqual(ws.cell(8, 21).value, "note")

    def test_dnra_shifted_tax_columns(self):
        """Portal headers sit one column left on B2B-DNRA; values must still land right."""
        raw = {
            "docdata": {
                "itcrev": {
                    "cdnra": [
                        {
                            "ctin": GSTIN_2B,
                            "trdnm": "X",
                            "nt": [
                                {
                                    "ntnum": "DN-1",
                                    "items": [
                                        {"txval": 100, "igst": 18, "cgst": 0, "sgst": 0, "cess": 0},
                                        {"txval": 100, "igst": 18, "cgst": 0, "sgst": 0, "cess": 0},
                                    ],
                                }
                            ],
                        }
                    ]
                }
            }
        }
        ws = _build(GSTR2BExporter, GSTIN_2B, PERIOD_2B, raw)["B2B-DNRA"]
        self.assertEqual(ws.cell(8, 6).value, "DN-1")  # revised note number
        self.assertEqual(ws.cell(8, 14).value, 200)  # taxable value
        self.assertEqual(ws.cell(8, 15).value, 36)  # integrated tax
        self.assertEqual(ws.cell(8, 18).value, 0)  # cess

    def test_formula_looking_text_stays_text(self):
        """A supplier can put "=..." in a number or name; the cell must not run it."""
        raw = {
            "docdata": {"b2b": [{"ctin": GSTIN_2B, "trdnm": '=HYPERLINK("x")', "inv": [{"inum": "=1+1"}]}]}
        }
        ws = _build(GSTR2BExporter, GSTIN_2B, PERIOD_2B, raw)["B2B"]
        self.assertEqual((ws.cell(7, 2).data_type, ws.cell(7, 2).value), ("s", '=HYPERLINK("x")'))
        self.assertEqual((ws.cell(7, 3).data_type, ws.cell(7, 3).value), ("s", "=1+1"))


class TestGSTR2AExport(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wb = _build(GSTR2AExporter, GSTIN_2A, PERIOD_2A, RAW_2A, supplier_names={})

    def test_item_rows_total_and_separator(self):
        """Item rows, a "-Total" row, a blank separator. Missing taxes read 0."""
        ws = self.wb["B2B"]
        self.assertEqual(ws.cell(7, 3).value, "INV-001")
        self.assertEqual(ws.cell(7, 5).value, "10-05-2024")
        self.assertEqual([ws.cell(7, c).value for c in (9, 10, 11, 12, 13)], [18, 10000, 0, 900, 900])
        self.assertEqual([ws.cell(8, c).value for c in (9, 10, 11, 12, 13)], [5, 2000, 100, 0, 0])
        self.assertEqual(ws.cell(9, 3).value, "INV-001-Total")
        self.assertEqual(ws.cell(9, 9).value, "-")
        self.assertEqual([ws.cell(9, c).value for c in (10, 11, 12, 13)], [12000, 100, 900, 900])
        self.assertIsNone(ws.cell(10, 1).value)
        self.assertIsNone(ws.cell(10, 3).value)

    def test_isd_document_routing(self):
        """One docnum lands in the invoice or credit-note pair by doc type; the other stays blank."""
        ws = self.wb["ISD"]
        self.assertEqual(ws.cell(7, 4).value, "ISD")
        self.assertEqual(ws.cell(7, 5).value, "S0080")
        self.assertEqual(ws.cell(7, 6).value, "03-03-2016")
        self.assertIsNone(ws.cell(7, 7).value)
        self.assertIsNone(ws.cell(7, 8).value)
        self.assertEqual(ws.cell(8, 4).value, "ISDCN")
        self.assertIsNone(ws.cell(8, 5).value)
        self.assertIsNone(ws.cell(8, 6).value)
        self.assertEqual(ws.cell(8, 7).value, "CN-1")
        self.assertEqual(ws.cell(8, 8).value, "04-03-2016")

    def test_b2ba_amendment_columns(self):
        """Amendment sheets word these columns differently; aspd and atyp still land."""
        raw = {
            "b2ba": [
                {
                    "ctin": GSTIN_2A,
                    "trdnm": "Acme",
                    "inv": [
                        {
                            "inum": "INV-9",
                            "oinum": "INV-1",
                            "aspd": "Apr-24",
                            "atyp": "R",
                            "itms": [{"itm_det": {"rt": 18, "txval": 100, "iamt": 18}}],
                        }
                    ],
                }
            ]
        }
        ws = _build(GSTR2AExporter, GSTIN_2A, PERIOD_2A, raw, supplier_names={})["B2BA"]
        row = next(r for r in range(7, ws.max_row + 1) if ws.cell(r, 6).value == "INV-9")
        self.assertEqual(ws.cell(row, 22).value, "R")  # amendment made, if any
        self.assertEqual(ws.cell(row, 23).value, "Apr-24")  # original tax period reported

    def test_amendment_total_row_marks_the_revised_document(self):
        """Prefixed headers: total row still blanks rate and marks the revised number."""
        raw = {
            "b2ba": [
                {
                    "ctin": GSTIN_2A,
                    "inv": [
                        {
                            "inum": "REV-9",
                            "oinum": "ORIG-1",
                            "itms": [
                                {"itm_det": {"rt": 18, "txval": 100, "iamt": 18}},
                                {"itm_det": {"rt": 5, "txval": 50, "iamt": 2.5}},
                            ],
                        }
                    ],
                }
            ]
        }
        ws = _build(GSTR2AExporter, GSTIN_2A, PERIOD_2A, raw, supplier_names={})["B2BA"]
        total = next(r for r in range(8, ws.max_row + 1) if ws.cell(r, 6).value == "REV-9-Total")

        self.assertEqual(ws.cell(total, 1).value, "ORIG-1")
        self.assertEqual(ws.cell(total, 11).value, "-")  # rate, never a sum of rates
        self.assertEqual(ws.cell(total, 12).value, 150)  # taxable value
        self.assertEqual(ws.cell(total, 13).value, 20.5)  # integrated tax

    def test_tcs_computed_and_group_fields(self):
        """Operator name from the group, period from the export, returned value = gross - net."""
        ws = self.wb["TCS"]
        self.assertEqual(ws.cell(7, 1).value, "27AAECS1234F1Z5")
        # operator not cached locally: blank, never a live lookup
        self.assertIsNone(ws.cell(7, 2).value)
        self.assertEqual(ws.cell(7, 3).value, PERIOD_2A)
        self.assertEqual(ws.cell(7, 4).value, 1000)
        self.assertEqual(ws.cell(7, 5).value, 100)
        self.assertEqual(ws.cell(7, 6).value, 900)

    def test_cdnr_reads_the_gov_cdn_key(self):
        """Stored 2A raw keeps the portal's `cdn`/`cdna` section keys, not the category names."""
        raw = {
            "cdn": [
                {
                    "ctin": GSTIN_2A,
                    "cfs": "Y",
                    "nt": [
                        {
                            "ntty": "C",
                            "nt_num": "CN-7",
                            "nt_dt": "23-09-2024",
                            "val": 118,
                            "itms": [{"itm_det": {"rt": 18, "txval": 100, "iamt": 18}}],
                        }
                    ],
                }
            ]
        }
        ws = _build(GSTR2AExporter, GSTIN_2A, PERIOD_2A, raw, supplier_names={})["CDNR"]
        row_values = [ws.cell(7, c).value for c in range(1, ws.max_column + 1)]
        self.assertIn("CN-7", row_values)
        self.assertIn(GSTIN_2A, row_values)

    def test_impgsez_supplier_from_sgstin(self):
        """SEZ imports carry the supplier as sgstin/tdname, not ctin/trdnm."""
        raw = {
            "impgsez": [
                {
                    "sgstin": "29ABCDE1234F1Z5",
                    "tdname": "SEZ Supplier",
                    "benum": "BE9",
                    "txval": 500,
                    "iamt": 90,
                }
            ]
        }
        ws = _build(GSTR2AExporter, GSTIN_2A, PERIOD_2A, raw, supplier_names={})["IMPG SEZ"]
        self.assertEqual(ws.cell(7, 1).value, "29ABCDE1234F1Z5")
        self.assertEqual(ws.cell(7, 2).value, "SEZ Supplier")
        self.assertEqual(ws.cell(7, 5).value, "BE9")  # bill of entry number

    def test_readme_generation_date_is_the_sync_time(self):
        """2A raw carries no generation date; the day the portal was read stands in."""
        period = "072024"
        store_raw_return_data(GSTIN_2B, ReturnType.GSTR2A.value, period, {"b2b": []})
        wb = _build(GSTR2AExporter, GSTIN_2B, period, RAW_2A, supplier_names={})
        self.assertEqual(wb["Read me"].cell(4, 5).value, now_datetime().strftime("%d-%m-%Y"))

    def test_matches_golden_workbook(self):
        """Every sheet matches the committed 2A golden."""
        golden = openpyxl.load_workbook(get_data_file_path(GOLDEN_2A))
        self.assertEqual(self.wb.sheetnames, golden.sheetnames)
        for sheet in golden.sheetnames:
            self.assertEqual(
                _cells(self.wb[sheet]), _cells(golden[sheet]), msg=f"cell mismatch in sheet {sheet!r}"
            )

    def test_tcs_period_follows_the_month_the_record_came_from(self):
        """A merged workbook holds several months; each TCS row names its own."""
        _name, wb = _build_periods(GSTR2AExporter, GSTIN_2A, [PERIOD_2A, "062024"], RAW_2A, supplier_names={})
        ws = wb["TCS"]
        self.assertEqual([ws.cell(row, 3).value for row in (7, 8)], [PERIOD_2A, "062024"])

    def test_multi_period_merges_invoice_blocks(self):
        """Two periods: invoice blocks repeat, name joins both."""
        single_rows = _data_row_count(self.wb["B2B"])

        name, wb = _build_periods(GSTR2AExporter, GSTIN_2A, [PERIOD_2A, "062024"], RAW_2A, supplier_names={})

        self.assertEqual(_data_row_count(wb["B2B"]), 2 * single_rows)
        self.assertIn(f"{PERIOD_2A}_062024", name)


class TestPeriodGrouping(IntegrationTestCase):
    """Groups follow the financial year, never across it."""

    FY_2024_25: ClassVar[list] = ["042024", "052024", "062024", "072024", "082024", "092024"]

    def test_monthly_gives_one_group_per_period(self):
        self.assertEqual(group_periods(self.FY_2024_25, "monthly"), [[p] for p in self.FY_2024_25])

    def test_quarterly_splits_on_fiscal_quarters(self):
        self.assertEqual(
            group_periods(self.FY_2024_25, "quarterly"),
            [["042024", "052024", "062024"], ["072024", "082024", "092024"]],
        )

    def test_half_yearly_and_yearly_keep_the_range_together(self):
        self.assertEqual(group_periods(self.FY_2024_25, "half_yearly"), [self.FY_2024_25])
        self.assertEqual(group_periods(self.FY_2024_25, "yearly"), [self.FY_2024_25])

    def test_groups_never_straddle_a_financial_year(self):
        """Feb-May spans two financial years, so two groups."""
        self.assertEqual(
            group_periods(["022024", "032024", "042024", "052024"], "quarterly"),
            [["022024", "032024"], ["042024", "052024"]],
        )

    def test_yearly_splits_across_financial_years(self):
        self.assertEqual(
            group_periods(["032024", "042024"], "yearly"),
            [["032024"], ["042024"]],
        )

    def test_groups_come_back_in_chronological_order(self):
        self.assertEqual(
            group_periods(["062024", "012025", "042024"], "monthly"),
            [["042024"], ["062024"], ["012025"]],
        )

    def test_all_clubs_every_period_into_one_group(self):
        self.assertEqual(
            group_periods(["042024", "032024"], "all"),
            [["032024", "042024"]],
        )


class TestGroupedExport(IntegrationTestCase):
    """Several groups arrive as a zip, one workbook each."""

    STEM_2A = f"GSTR-2A-{GSTIN_2A}"

    def _export(self, periods, group_by):
        with _mock_names(RAW_2A), patch.object(GSTR2AExporter, "_supplier_names", lambda self, gstins: {}):
            return build_export(GSTIN_2A, "GSTR-2A", periods, group_by)

    def test_single_group_stays_a_bare_workbook(self):
        file_name, content = self._export(["042024", "052024", "062024"], "quarterly")

        self.assertTrue(file_name.endswith(".xlsx"))
        self.assertIn("042024_062024", file_name)
        self.assertIn("B2B", _load(content).sheetnames)

    def test_multiple_groups_are_zipped_one_workbook_each(self):
        file_name, content = self._export(["042024", "052024", "062024"], "monthly")

        self.assertTrue(file_name.endswith(".zip"))
        with ZipFile(BytesIO(content)) as archive:
            names = archive.namelist()
            self.assertEqual(
                names,
                [f"{self.STEM_2A}-{period}.xlsx" for period in ("042024", "052024", "062024")],
            )
            # each entry is a real workbook, not a stub
            ws = _load(archive.read(names[0]))["B2B"]
            self.assertEqual(ws.cell(7, 1).value, GSTIN_2A)

    def test_empty_groups_are_skipped_not_fatal(self):
        """One unsynced month must not sink the rest of the range."""
        raw_by_period = {"042024": RAW_2A, "052024": None}

        with (
            patch(
                f"{ENGINE_MODULE}.get_raw_return_data",
                side_effect=lambda gstin, return_type, period: raw_by_period[period],
            ),
            patch.object(GovReturnExporter, "get_gstin_names", staticmethod(lambda gstin: {})),
            patch.object(GSTR2AExporter, "_supplier_names", lambda self, gstins: {}),
        ):
            file_name, content = build_export(GSTIN_2A, "GSTR-2A", ["042024", "052024"], "monthly")

        self.assertTrue(file_name.endswith(".zip"))
        with ZipFile(BytesIO(content)) as archive:
            self.assertEqual(archive.namelist(), [f"{self.STEM_2A}-042024.xlsx"])

    def test_all_groups_empty_still_throws(self):
        with (
            patch(f"{ENGINE_MODULE}.get_raw_return_data", return_value=None),
            self.assertRaises(frappe.ValidationError),
        ):
            build_export(GSTIN_2A, "GSTR-2A", ["042024", "052024"], "monthly")


class TestSheetRowSpill(IntegrationTestCase):
    """A section with more rows than Excel allows continues on "<sheet> Part N"."""

    def test_overflow_continues_on_a_part_sheet(self):
        # data starts at row 7, so this leaves room for 2 rows per sheet
        with patch(f"{ENGINE_MODULE}.EXCEL_MAX_ROW", 8):
            wb = _build(GSTR2AExporter, GSTIN_2A, PERIOD_2A, RAW_2A, supplier_names={})

        self.assertIn("B2B Part 2", wb.sheetnames)

        first, second = wb["B2B"], wb["B2B Part 2"]
        # 2A B2B here is 4 rows (2 item rows, a total row, a blank separator)
        self.assertEqual(first.cell(7, 1).value, GSTIN_2A)
        self.assertEqual(first.cell(8, 1).value, GSTIN_2A)
        self.assertEqual(second.cell(7, 1).value, GSTIN_2A)

        # the continuation carries the template's headers and merges, not just values
        self.assertEqual(_cells(first)[(5, 1)], _cells(second)[(5, 1)])
        self.assertEqual(len(first.merged_cells.ranges), len(second.merged_cells.ranges))

    def test_no_part_sheet_when_everything_fits(self):
        wb = _build(GSTR2AExporter, GSTIN_2A, PERIOD_2A, RAW_2A, supplier_names={})
        self.assertNotIn("B2B Part 2", wb.sheetnames)


class TestGSTR2ExportIntegration(IntegrationTestCase):
    """Store the payload, build through the public entry point."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.raw = parse_json(read_file(get_data_file_path("test_gstr_2b_v4_0.json")))["data"]
        store_raw_return_data(GSTIN_2B, ReturnType.GSTR2B.value, PERIOD_2B, cls.raw)

    @patch.object(
        GovReturnExporter,
        "get_gstin_names",
        staticmethod(
            lambda gstin: {
                "business_name": MOCK_BUSINESS,
                "legal_name": MOCK_LEGAL,
                "trade_name": MOCK_TRADE,
            }
        ),
    )
    def test_build_export_from_stored_payload(self):
        file_name, content = build_export(GSTIN_2B, "GSTR-2B", [PERIOD_2B])
        self.assertTrue(file_name.endswith(".xlsx"))
        self.assertIn(GSTIN_2B, file_name)

        ws = _load(content)["B2B"]
        self.assertEqual(ws.cell(7, 1).value, GSTIN_2B)
        self.assertEqual(ws.cell(7, 3).value, "S008400")


class TestSupplierNamesAreBatched(IntegrationTestCase):
    """One name query for the whole payload, not one per supplier."""

    SUPPLIERS: ClassVar[list] = [f"24AACT{i:04d}F1Z5" for i in range(5)]

    def setUp(self):
        for gstin in self.SUPPLIERS:
            frappe.get_doc({"doctype": "GSTIN", "gstin": gstin, "legal_name": f"LEGAL {gstin}"}).insert(
                ignore_permissions=True
            )

    def tearDown(self):
        for gstin in self.SUPPLIERS:
            frappe.db.delete("GSTIN", {"gstin": gstin})

    def _raw(self):
        return {
            "b2b": [
                {"ctin": gstin, "inv": [{"inum": f"INV-{gstin}", "idt": "10-05-2024", "val": 100}]}
                for gstin in self.SUPPLIERS
            ],
            # SEZ imports key the supplier as sgstin, so the batch must look there too
            "impgsez": [{"sgstin": self.SUPPLIERS[0], "benum": "1", "bedt": "10-05-2024"}],
        }

    def test_registry_is_read_once_not_per_supplier(self):
        per_gstin = Mock(return_value={})
        with (
            patch(f"{ENGINE_MODULE}.get_raw_return_data", return_value=self._raw()),
            patch.object(GSTR2AExporter, "_supplier_names", lambda self, gstins: {}),
            patch.object(GovReturnExporter, "get_gstin_names", staticmethod(per_gstin)),
        ):
            _, content = GSTR2AExporter(GSTIN_2A, [PERIOD_2A]).build()

        ws = _load(content)["B2B"]
        self.assertEqual(ws.cell(7, 2).value, f"LEGAL {self.SUPPLIERS[0]}")

        # only the company's own GSTIN is looked up, for the Read me
        looked_up = {call.args[0] for call in per_gstin.call_args_list}
        self.assertEqual(looked_up - {GSTIN_2A}, set())

    def test_handles_a_large_supplier_set_in_one_query(self):
        """IN list is unchunked on purpose; 12k GSTINs must still be one statement."""
        many = [f"24AACT{i:04d}F1Z5" for i in range(12_000)]
        docdata = {"b2b": [{"ctin": g} for g in many]}

        statements = []
        real = frappe.db.sql

        def counting(query, *a, **k):
            statements.append(query)
            return real(query, *a, **k)

        exporter = GSTR2AExporter.__new__(GSTR2AExporter)
        with patch.object(frappe.db, "sql", counting):
            names = exporter._gstin_record_names(exporter._raw_gstins(docdata))

        lookups = [q for q in statements if "tabGSTIN" in q]
        self.assertEqual(len(lookups), 1, "supplier lookup was split across statements")
        # only the seeded rows exist, but all 12k were queried without error
        self.assertEqual(len(names), len(self.SUPPLIERS))


class TestSupplierNameSource(IntegrationTestCase):
    """Historical rows can carry different names for one GSTIN; the newest row's name wins."""

    SUPPLIER = "24AACT9999F1Z5"

    def _inward_supply(self, name, modified):
        row = frappe.get_doc(
            {
                "doctype": "GST Inward Supply",
                "company_gstin": GSTIN_2A,
                "supplier_gstin": self.SUPPLIER,
                "supplier_name": name,
                "bill_no": f"INV-{name[:4]}",
                "bill_date": "2024-05-10",
                "classification": "B2B",
                "doc_type": "Invoice",
            }
        ).insert(ignore_permissions=True)
        frappe.db.set_value("GST Inward Supply", row.name, "modified", modified, update_modified=False)

    def test_newest_row_names_the_supplier(self):
        self._inward_supply("Zeta Legacy Traders", "2024-01-01 00:00:00")
        self._inward_supply("Acme Current Traders", "2025-01-01 00:00:00")

        exporter = GSTR2AExporter.__new__(GSTR2AExporter)
        exporter.gstin = GSTIN_2A
        self.assertEqual(exporter._supplier_names({self.SUPPLIER}), {self.SUPPLIER: "Acme Current Traders"})


class TestExportFileLifecycle(IntegrationTestCase):
    """Generated exports are scratch files: handed over on download, swept if abandoned."""

    PERIOD = "082020"
    FROM_DATE = "2020-08-01"
    TO_DATE = "2020-08-31"
    LOG = f"GSTR2b-{PERIOD}-{GSTIN_2B}"

    def setUp(self):
        # download matches on the request, so the month must look synced
        store_raw_return_data(
            GSTIN_2B,
            ReturnType.GSTR2B.value,
            self.PERIOD,
            {"docdata": {"b2b": [{"ctin": GSTIN_2B}]}},
        )
        patcher = patch("india_compliance.gst_india.utils.validate_company_gstin_access")
        patcher.start()
        self.addCleanup(patcher.stop)

    def _download(self, from_date=FROM_DATE, to_date=TO_DATE):
        return download_export_file(GSTIN_2B, "GSTR-2B", from_date, to_date, "all")

    def _make_export_file(self, creation=None, **overrides):
        file = frappe.get_doc(
            {
                "doctype": "File",
                "file_name": f"GSTR-2B-{GSTIN_2B}-{self.PERIOD}.xlsx",
                "attached_to_doctype": RETURN_LOG,
                "attached_to_name": self.LOG,
                "attached_to_field": export_key([self.PERIOD], "all"),
                "is_private": 1,
                "content": b"not-a-real-xlsx",
                **overrides,
            }
        ).insert(ignore_permissions=True)
        _remove_file_later(self, file)

        if creation:
            frappe.db.set_value("File", file.name, "creation", creation, update_modified=False)
        return file.name

    def test_download_streams_the_file(self):
        self._make_export_file()

        with patch("frappe.utils.response.send_private_file") as send:
            self._download()

        self.assertTrue(send.called, "file was never handed to the browser")
        self.assertTrue(send.call_args.args[0].startswith("/files/"), send.call_args)
        # name comes from the request, not the File row
        file_name = f"GSTR-2B-{GSTIN_2B}-{self.PERIOD}.xlsx"
        self.assertEqual(send.call_args.kwargs["filename"], file_name)
        send.return_value.headers.__setitem__.assert_called_once_with(
            "Content-Disposition", f"attachment; filename*=UTF-8''{file_name}"
        )

    def test_download_is_shared_between_users(self):
        """One build serves everyone allowed the GSTIN."""
        name = self._make_export_file()
        frappe.db.set_value("File", name, "owner", "someone-else@example.com", update_modified=False)

        with patch("frappe.utils.response.send_private_file") as send:
            self._download()

        self.assertTrue(send.called, "an export built by someone else was rebuilt instead of reused")

    def test_download_refuses_when_nothing_was_built(self):
        with self.assertRaises(frappe.DoesNotExistError):
            self._download()

    def test_download_never_serves_a_file_outside_the_private_store(self):
        """File rows are user-writable; a public-store row must not stream."""
        self._make_export_file(is_private=0)

        with self.assertRaises(frappe.DoesNotExistError):
            self._download()

    def test_download_never_serves_a_file_not_named_for_the_request(self):
        """Any user can attach a File row pointing at any private path; only our own build may stream."""
        raw_url = frappe.db.get_value(
            "File", {"attached_to_name": self.LOG, "attached_to_field": "raw_gov_data"}, "file_url"
        )
        self._make_export_file(file_name=None, file_url=raw_url, content=None)

        with self.assertRaises(frappe.DoesNotExistError):
            self._download()

    def test_download_ignores_a_same_named_file_of_another_request(self):
        """Same GSTIN and first month, different range: the key must split them."""
        self._make_export_file(attached_to_field=export_key([self.PERIOD, "092020"], "all"))

        with self.assertRaises(frappe.DoesNotExistError):
            self._download()

    def test_sweep_drops_only_abandoned_files(self):
        stale = self._make_export_file(creation=add_days(now_datetime(), -3))
        fresh = self._make_export_file()

        delete_stale_export_files()

        self.assertFalse(frappe.db.exists("File", stale))
        self.assertTrue(frappe.db.exists("File", fresh), "swept a file the user may still download")

    def test_sweep_spares_the_logs_own_attachments(self):
        """The synced payload is a File on the same log. Old is normal for it."""
        raw_file = frappe.db.get_value(
            "File",
            {
                "attached_to_doctype": RETURN_LOG,
                "attached_to_name": self.LOG,
                "attached_to_field": "raw_gov_data",
            },
        )
        frappe.db.set_value("File", raw_file, "creation", add_days(now_datetime(), -3), update_modified=False)

        delete_stale_export_files()

        self.assertTrue(frappe.db.exists("File", raw_file), "swept the synced data itself")

    def _generate(self, period=PERIOD, invoices=("R1",)):
        raw = {"docdata": {"b2b": [{"ctin": GSTIN_2B, "inv": [{"inum": inum} for inum in invoices]}]}}
        month = f"{period[2:]}-{period[:2]}-01"
        with _mock_names(raw), patch("frappe.publish_realtime"):
            generate_export_file(GSTIN_2B, "GSTR2b", month, month, "Administrator", "all")

        file = frappe.get_last_doc(
            "File",
            {
                "attached_to_field": export_key([period], "all"),
                "attached_to_name": f"GSTR2b-{period}-{GSTIN_2B}",
            },
        )
        _remove_file_later(self, file)
        return file

    def test_built_export_hangs_off_the_log(self):
        """The log's company is what gates the file."""
        file = self._generate()
        self.assertEqual((file.attached_to_doctype, file.attached_to_name), (RETURN_LOG, self.LOG))

    def test_rebuild_after_resync_is_downloadable(self):
        """Old file keeps the clean name, frappe suffixes the new one; download must not care."""
        period, raw = "092020", {"docdata": {"b2b": [{"ctin": GSTIN_2B}]}}
        store_raw_return_data(GSTIN_2B, ReturnType.GSTR2B.value, period, raw)
        self._generate(period)
        store_raw_return_data(GSTIN_2B, ReturnType.GSTR2B.value, period, raw)  # resync

        file = self._generate(period, invoices=("R1", "R2"))  # new data, new bytes
        self.assertNotEqual(file.file_name, f"GSTR-2B-{GSTIN_2B}-{period}.xlsx", "old file gone?")
        with patch("frappe.utils.response.send_private_file") as send:
            self._download("2020-09-01", "2020-09-30")
        self.assertEqual(send.call_args.args[0], file.file_url.split("/private", 1)[1])
        self.assertEqual(send.call_args.kwargs["filename"], f"GSTR-2B-{GSTIN_2B}-{period}.xlsx")


class TestExportReuse(IntegrationTestCase):
    """Repeat clicks within a day serve the file already built; a resync forces a rebuild."""

    PERIODS: ClassVar[list] = ["052024"]

    def setUp(self):
        self.raw = {"docdata": {"b2b": [{"ctin": GSTIN_2B, "trdnm": "X", "inv": [{"inum": "R1"}]}]}}
        store_raw_return_data(GSTIN_2B, ReturnType.GSTR2B.value, self.PERIODS[0], self.raw)
        self.file_name = export_file_name(GSTIN_2B, "GSTR-2B", self.PERIODS, "all")

    def test_endpoint_name_matches_built_name(self):
        """Lookup name and built name must not drift."""
        with _mock_names(self.raw):
            built_name, _ = build_export(GSTIN_2B, "GSTR-2B", self.PERIODS, "all")
        self.assertEqual(built_name, self.file_name)

    def test_fresh_file_reused_then_resync_rebuilds(self):
        args = (GSTIN_2B, "GSTR-2B", self.PERIODS, "all")
        self.assertIsNone(get_reusable_export(*args))

        file = frappe.get_doc(
            {
                "doctype": "File",
                "file_name": self.file_name,
                "attached_to_doctype": RETURN_LOG,
                "attached_to_name": f"GSTR2b-{self.PERIODS[0]}-{GSTIN_2B}",
                "attached_to_field": export_key(self.PERIODS, "all"),
                "is_private": 1,
                "content": b"built-export",
            }
        ).insert(ignore_permissions=True)
        _remove_file_later(self, file)
        self.assertEqual(get_reusable_export(*args), file.file_url)

        # resync bumps the log; the built file is now older than the data
        store_raw_return_data(GSTIN_2B, ReturnType.GSTR2B.value, self.PERIODS[0], self.raw)
        self.assertIsNone(get_reusable_export(*args))

    def test_grouping_variants_do_not_share_a_zip(self):
        periods = ["042024", "052024", "062024", "072024"]
        monthly = export_file_name(GSTIN_2B, "GSTR-2B", periods, "monthly")
        quarterly = export_file_name(GSTIN_2B, "GSTR-2B", periods, "quarterly")
        self.assertNotEqual(monthly, quarterly)


class TestGSTINNameLookup(IntegrationTestCase):
    """Names come off the cached GSTIN row only. Nothing cached, nothing shown."""

    def tearDown(self):
        frappe.db.delete("GSTIN", {"gstin": GSTIN_2A})

    def test_reads_the_cached_row_or_nothing(self):
        self.assertEqual(GovReturnExporter.get_gstin_names(GSTIN_2A), {})

        frappe.get_doc(
            {"doctype": "GSTIN", "gstin": GSTIN_2A, "legal_name": MOCK_LEGAL, "trade_name": MOCK_TRADE}
        ).insert(ignore_permissions=True)
        info = GovReturnExporter.get_gstin_names(GSTIN_2A)
        self.assertEqual((info.legal_name, info.trade_name), (MOCK_LEGAL, MOCK_TRADE))


class TestExportPermissions(IntegrationTestCase):
    """No export permission, no service."""

    USER = "export-noperms@example.com"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not frappe.db.exists("User", cls.USER):
            frappe.get_doc({"doctype": "User", "email": cls.USER, "first_name": "No Perms"}).insert(
                ignore_permissions=True
            )

    def tearDown(self):
        frappe.set_user("Administrator")

    def test_export_endpoint_requires_permission(self):
        from india_compliance.gst_india.doctype.gst_return_export.gst_return_export import (
            export_return_as_excel,
        )

        frappe.set_user(self.USER)
        with self.assertRaises(frappe.PermissionError):
            export_return_as_excel(GSTIN_2B, "GSTR-2B", "2020-03-01", "2020-03-31")

    def test_download_requires_permission(self):
        frappe.set_user(self.USER)
        with self.assertRaises(frappe.PermissionError):
            download_export_file(GSTIN_2B, "GSTR-2B", "2020-03-01", "2020-03-31")

    def test_period_bounds_require_permission(self):
        doc_ = frappe.get_doc(DOCTYPE)
        frappe.set_user(self.USER)
        with self.assertRaises(frappe.PermissionError):
            doc_.get_period_bounds("GSTR-2B")
