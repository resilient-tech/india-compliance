# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

"""Catch a template change before a customer does. Run me after refreshing a template."""

from typing import ClassVar

import openpyxl
from frappe.tests import IntegrationTestCase

from india_compliance.gst_india.doctype.gst_return_export.gstr_2_export import (
    EXPORTERS,
    NOT_FILLED,
)
from india_compliance.gst_india.doctype.gst_return_export.template_exporter import (
    column_labels,
    header_extent,
)
from india_compliance.gst_india.utils import get_data_file_path


class TestTemplateCoverage(IntegrationTestCase):
    """The goldens only see columns their fixture fills. These see every column."""

    # 2B rows carry no per-document rate
    KNOWN_BLANK: ClassVar[set] = {("gstr2b_excel_template_v1.1.xlsx", "B2B-DNRA", "revised details | rate")}

    def document_tabs(self, exporter):
        """Sheets the field maps fill: not Read me, not the ITC summaries."""
        workbook = openpyxl.load_workbook(get_data_file_path(exporter.template))
        tabs = [s for s in workbook.sheetnames if s != "Read me" and not s.startswith("ITC")]
        return workbook, tabs

    def test_every_sheet_is_listed(self):
        """A tab left out of SHEETS exports empty and says nothing."""
        for return_type, exporter in EXPORTERS.items():
            with self.subTest(return_type):
                _workbook, tabs = self.document_tabs(exporter)
                self.assertEqual(set(tabs) - set(exporter.SHEETS), set())

    def test_every_column_is_filled_by_something(self):
        """A column nothing maps to is blank for every customer. Map it, or list it above."""
        for return_type, exporter in EXPORTERS.items():
            workbook, tabs = self.document_tabs(exporter)
            blank = [
                (sheet, label)
                for sheet in tabs
                if exporter.SHEETS.get(sheet) is not NOT_FILLED
                for label in column_labels(workbook[sheet], header_extent(workbook[sheet])[0]).values()
                if label
                and not exporter.spec_for(label, sheet)
                and (exporter.template, sheet, label) not in self.KNOWN_BLANK
            ]
            with self.subTest(return_type):
                self.assertEqual(blank, [])
