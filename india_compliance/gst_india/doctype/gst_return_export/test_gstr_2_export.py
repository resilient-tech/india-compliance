# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

"""
Tests for the GSTR-2A / 2B Excel exporter (gstr_2_export.py): per-cell value assertions
for the tricky logic, plus committed golden workbooks (gst_india/data) as regression nets.
Mocked unit builds for coverage, one integration test through build_export.
"""

from contextlib import ExitStack, contextmanager
from io import BytesIO
from unittest.mock import patch

import openpyxl
from frappe import parse_json, read_file
from frappe.tests import IntegrationTestCase

from india_compliance.gst_india.doctype.gst_return_export.gstr_2_export import (
    GovReturnExporter,
    GSTR2AExporter,
    GSTR2BExporter,
    build_export,
)
from india_compliance.gst_india.doctype.gst_return_log.gst_return_log import (
    store_raw_return_data,
)
from india_compliance.gst_india.utils import get_data_file_path
from india_compliance.gst_india.utils.gstr_utils import ReturnType

EXPORT_MODULE = "india_compliance.gst_india.doctype.gst_return_export.gstr_2_export"

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
    """{(row, col): value} for every non-empty cell — the comparable content of a sheet."""
    return {
        (cell.row, cell.column): cell.value
        for row in ws.iter_rows()
        for cell in row
        if cell.value not in (None, "")
    }


def _data_row_count(ws, start=7, col=1):
    """Number of data rows (non-empty first column) below the header block."""
    return sum(1 for r in range(start, ws.max_row + 1) if ws.cell(r, col).value not in (None, ""))


@contextmanager
def _mock_names(raw):
    """Feed the raw payload and mock registry name lookups deterministically."""
    with ExitStack() as stack:
        stack.enter_context(patch(f"{EXPORT_MODULE}.get_raw_return_data", return_value=raw))
        stack.enter_context(
            patch.object(
                GovReturnExporter,
                "_live_gstin_info",
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


def _build_periods(exporter_cls, gstin, periods, raw, supplier_names=None):
    """Build over one or more periods; return (file_name, workbook). The mocked lookup
    returns `raw` for each period, so multiple periods exercise the merge."""
    with _mock_names(raw) as stack:
        if supplier_names is not None:
            stack.enter_context(patch.object(GSTR2AExporter, "_supplier_names", lambda self: supplier_names))
        name, content = exporter_cls(gstin, periods).build()
    return name, _load(content)


def _build(exporter_cls, gstin, period, raw, supplier_names=None):
    """Single-period build; return just the workbook."""
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
        """Two periods: document sections concatenate, itcsumm sums, the Read me reflects
        the last period, and the file name joins the periods."""
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
        """Bills of entry split by isamd: original -> IMPG, amended ('Y') -> IMPGA with the
        amendment type. The payload has no separate impga section."""
        raw = {
            "impg": [
                {"boenum": "BE-ORIG", "isamd": "N", "txval": 100, "igst": 18, "cess": 0},
                {"boenum": "BE-AMD", "isamd": "Y", "amendType": "A", "txval": 200, "igst": 36, "cess": 0},
            ]
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
        wb = _build(GSTR2BExporter, GSTIN_2B, PERIOD_2B, raw)
        self.assertEqual(wb["IMPGSEZ"].cell(7, 1).value, "29ABCDE1234F1Z5")
        self.assertEqual(wb["IMPGSEZ"].cell(7, 5).value, "S-ORIG")
        self.assertEqual(wb["IMPGSEZA"].cell(7, 5).value, "S-AMD")
        self.assertEqual(wb["IMPGSEZA"].cell(7, 10).value, "Addition")  # type of amendment (G)

    def test_itc_reversal_sums_items(self):
        """ITC-reversal invoices carry tax only in items; the sheet shows the summed
        invoice-level taxable value and tax (one row per document)."""
        raw = {
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
        ws = _build(GSTR2BExporter, GSTIN_2B, PERIOD_2B, raw)["B2B (ITC Reversal)"]
        self.assertEqual(ws.cell(7, 3).value, "REV-1")
        self.assertEqual(ws.cell(7, 9).value, 150)  # taxable value (summed)
        self.assertEqual(ws.cell(7, 10).value, 27)  # integrated tax (18 + 9)

    def test_itc_reduction_and_remarks_columns(self):
        """IMS ITC-reduction fields and remarks now map (blank when the payload omits them)."""
        raw = {
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
        ws = _build(GSTR2BExporter, GSTIN_2B, PERIOD_2B, raw)["B2BA"]
        self.assertEqual(ws.cell(8, 16).value, "Yes")  # whether itc to be reduced
        self.assertEqual([ws.cell(8, c).value for c in (17, 18, 19, 20)], [5, 2, 2, 1])
        self.assertEqual(ws.cell(8, 21).value, "note")

    def test_dnra_shifted_tax_columns(self):
        """B2B-DNRA's portal headers mis-merge Taxable Value / Tax Amount a column left;
        the summed taxable value and four taxes must still land in the right cells."""
        raw = {
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
        ws = _build(GSTR2BExporter, GSTIN_2B, PERIOD_2B, raw)["B2B-DNRA"]
        self.assertEqual(ws.cell(8, 6).value, "DN-1")  # revised note number
        self.assertEqual(ws.cell(8, 14).value, 200)  # taxable value
        self.assertEqual(ws.cell(8, 15).value, 36)  # integrated tax
        self.assertEqual(ws.cell(8, 18).value, 0)  # cess


class TestGSTR2AExport(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.wb = _build(GSTR2AExporter, GSTIN_2A, PERIOD_2A, RAW_2A, supplier_names={})

    def test_item_rows_total_and_separator(self):
        """One row per item, a per-invoice total row (number+"-Total", rate "-", taxes
        summed), then a blank separator. Codes/dates verbatim; missing taxes coerced to 0."""
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
        """A single docnum/docdt routes to the invoice or credit-note column by doc type;
        the other pair stays blank."""
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
        """Amendment sheets label the amended period / amendment type differently from the
        base sheets; `aspd` and `atyp` must still land in those columns (verbatim, like 2A)."""
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

    def test_tcs_computed_and_group_fields(self):
        """TCS: operator name from the group, tax period is the export period, and value of
        supplies returned is computed as gross - net-liable."""
        ws = self.wb["TCS"]
        self.assertEqual(ws.cell(7, 1).value, "27AAECS1234F1Z5")
        self.assertEqual(ws.cell(7, 2).value, MOCK_LEGAL)  # operator name = registered legal name
        self.assertEqual(ws.cell(7, 3).value, PERIOD_2A)
        self.assertEqual(ws.cell(7, 4).value, 1000)
        self.assertEqual(ws.cell(7, 5).value, 100)
        self.assertEqual(ws.cell(7, 6).value, 900)

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

    def test_matches_golden_workbook(self):
        """Regression net for 2A: every sheet's cell values match the committed golden
        (built from the inline test payload)."""
        golden = openpyxl.load_workbook(get_data_file_path(GOLDEN_2A))
        self.assertEqual(self.wb.sheetnames, golden.sheetnames)
        for sheet in golden.sheetnames:
            self.assertEqual(
                _cells(self.wb[sheet]), _cells(golden[sheet]), msg=f"cell mismatch in sheet {sheet!r}"
            )

    def test_multi_period_merges_invoice_blocks(self):
        """Two periods: 2A invoice blocks (item rows + total row) repeat across the merged
        sections, and the file name joins the periods."""
        single_rows = _data_row_count(self.wb["B2B"])

        name, wb = _build_periods(GSTR2AExporter, GSTIN_2A, [PERIOD_2A, "062024"], RAW_2A, supplier_names={})

        self.assertEqual(_data_row_count(wb["B2B"]), 2 * single_rows)
        self.assertIn(f"{PERIOD_2A}_062024", name)


class TestGSTR2ExportIntegration(IntegrationTestCase):
    """End-to-end: store the payload in GST Return Log, then build via the public entry point."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.raw = parse_json(read_file(get_data_file_path("test_gstr_2b_v4_0.json")))["data"]
        store_raw_return_data(GSTIN_2B, ReturnType.GSTR2B.value, PERIOD_2B, cls.raw)

    @patch.object(
        GovReturnExporter,
        "_live_gstin_info",
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
