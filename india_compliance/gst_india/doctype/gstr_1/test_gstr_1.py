# Copyright (c) 2024, Resilient Tech and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from india_compliance.gst_india.api_classes.taxpayer_returns import GSTR1API
from india_compliance.gst_india.doctype.gstr_1.gstr_1_export import (
    GovExcel,
    _filter_data_by_sections,
    _get_excel_sheet_names,
    _get_gov_filename,
    _get_selected_sections,
)
from india_compliance.gst_india.utils.exporter import ExcelExporter
from india_compliance.gst_india.utils.gstr_1 import (
    JSON_CATEGORY_EXCEL_CATEGORY_MAPPING,
    GovExcelSheetName,
    GovJsonKey,
)

# Every GovJsonKey value that maps to a sheet in JSON_CATEGORY_EXCEL_CATEGORY_MAPPING.
# sec_sum is excluded (no sheet mapping). Used for exhaustive template checks.
GOV_EXCEL_SECTIONS = frozenset(
    key.value for key in GovJsonKey if key.value in JSON_CATEGORY_EXCEL_CATEGORY_MAPPING
)


class TestGSTR1(IntegrationTestCase):
    pass


class TestGSTR1APIErrorHandling(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.api = GSTR1API.__new__(GSTR1API)
        cls.api.company_gstin = "01AABCE2207R1Z5"

    def test_no_invoices_found_is_ignored(self):
        # SUPECO section with no data returns RETWEB_04 with status_cd 0
        response = frappe._dict(
            {
                "error": {
                    "error_cd": "RETWEB_04",
                    "message": "No invoices found!!",
                },
                "status_cd": 0,
            }
        )

        self.api.handle_error_response(response)
        self.assertEqual(response.error_type, "no_docs_found")

    def test_unknown_error_code_raises(self):
        response = frappe._dict(
            {
                "error": {
                    "error_cd": "RETWEB_99",
                    "message": "Some other error",
                },
                "status_cd": 0,
            }
        )

        self.assertRaises(frappe.ValidationError, self.api.handle_error_response, response)


class TestGSTR1Export(IntegrationTestCase):
    GSTIN = "29AABCU9603R1ZM"
    PERIOD = "032024"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.gov_data = {
            "b2b": [{"invoice": "INV-001"}],
            "cdnr": [{"note": "CN-001"}],
            "b2cs": [{"supply": "S-001"}],
        }

    def test_returns_all_sections_when_section_is_none(self):
        result = _filter_data_by_sections(self.gov_data, None)
        self.assertEqual(result, self.gov_data)

    def test_returns_matching_section(self):
        result = _filter_data_by_sections(self.gov_data, ["b2b"])
        self.assertEqual(result, {"b2b": [{"invoice": "INV-001"}]})

    def test_returns_multiple_matching_sections(self):
        result = _filter_data_by_sections(self.gov_data, ["b2b", "cdnr"])
        self.assertEqual(
            result,
            {
                "b2b": [{"invoice": "INV-001"}],
                "cdnr": [{"note": "CN-001"}],
            },
        )

    def test_returns_empty_for_unknown_section(self):
        result = _filter_data_by_sections(self.gov_data, ["nonexistent"])
        self.assertEqual(result, {})

    def test_non_hsn_section_returns_single_key(self):
        self.assertEqual(_get_selected_sections("b2b", is_hsn_bifurcated=False), ["b2b"])

    def test_hsn_pre_bifurcation_returns_single_hsn_key(self):
        self.assertEqual(_get_selected_sections(GovJsonKey.HSN.value, is_hsn_bifurcated=False), ["hsn"])

    def test_hsn_post_bifurcation_returns_split_keys(self):
        self.assertEqual(
            _get_selected_sections(GovJsonKey.HSN.value, is_hsn_bifurcated=True),
            ["hsn_b2b", "hsn_b2c"],
        )

    def test_unknown_section_is_returned_as_is(self):
        self.assertEqual(_get_selected_sections("nonexistent", is_hsn_bifurcated=False), ["nonexistent"])

    def test_non_hsn_section_returns_single_sheet(self):
        self.assertEqual(
            _get_excel_sheet_names(_get_selected_sections("b2b", is_hsn_bifurcated=False)),
            [GovExcelSheetName.B2B.value],
        )

    def test_hsn_pre_bifurcation_returns_single_sheet(self):
        self.assertEqual(
            _get_excel_sheet_names(_get_selected_sections(GovJsonKey.HSN.value, is_hsn_bifurcated=False)),
            [GovExcelSheetName.HSN.value],
        )

    def test_hsn_post_bifurcation_returns_both_split_sheets(self):
        self.assertEqual(
            _get_excel_sheet_names(_get_selected_sections(GovJsonKey.HSN.value, is_hsn_bifurcated=True)),
            [GovExcelSheetName.HSN_B2B.value, GovExcelSheetName.HSN_B2C.value],
        )

    def test_supeco_resolves_to_eco_sheet(self):
        self.assertEqual(
            _get_excel_sheet_names(_get_selected_sections(GovJsonKey.SUPECOM.value, is_hsn_bifurcated=False)),
            [GovExcelSheetName.SUPECOM.value],
        )

    def test_unknown_section_returns_empty_list(self):
        self.assertEqual(
            _get_excel_sheet_names(_get_selected_sections("nonexistent", is_hsn_bifurcated=False)), []
        )

    def test_filename_no_sections(self):
        self.assertEqual(_get_gov_filename(self.GSTIN, self.PERIOD), f"GSTR-1-Gov-{self.GSTIN}-{self.PERIOD}")

    def test_filename_no_sections_explicit_none(self):
        self.assertEqual(
            _get_gov_filename(self.GSTIN, self.PERIOD, None), f"GSTR-1-Gov-{self.GSTIN}-{self.PERIOD}"
        )

    def test_filename_single_section(self):
        self.assertEqual(
            _get_gov_filename(self.GSTIN, self.PERIOD, ["b2b"]), f"GSTR-1-Gov-{self.GSTIN}-{self.PERIOD}-b2b"
        )

    def test_filename_multiple_sections(self):
        self.assertEqual(
            _get_gov_filename(self.GSTIN, self.PERIOD, ["b2b", "cdnr"]),
            f"GSTR-1-Gov-{self.GSTIN}-{self.PERIOD}-multi-section",
        )

    def _filter_sheets(self, template_version, sections):
        """Helper: load template, apply section filtering, return remaining sheet names."""
        is_hsn_bifurcated = template_version == "V2.1"
        if isinstance(sections, str):
            sections = [sections]
        selected = []
        for section in sections:
            selected.extend(_get_selected_sections(section, is_hsn_bifurcated))
        sheet_names = _get_excel_sheet_names(selected)
        excel = ExcelExporter(GovExcel.TEMPLATE_EXCEL_FILE[template_version])
        GovExcel()._filter_selected_section_sheets(excel, sheet_names)
        return set(excel.wb.sheetnames)

    def test_v20_b2b_keeps_only_b2b_and_master(self):
        result = self._filter_sheets("V2.0", "b2b")
        self.assertEqual(result, {GovExcelSheetName.MASTER.value, GovExcelSheetName.B2B.value})

    def test_v20_hsn_keeps_single_hsn_sheet(self):
        result = self._filter_sheets("V2.0", "hsn")
        self.assertEqual(result, {GovExcelSheetName.MASTER.value, GovExcelSheetName.HSN.value})

    def test_v21_hsn_keeps_both_bifurcated_sheets(self):
        result = self._filter_sheets("V2.1", "hsn")
        self.assertEqual(
            result,
            {
                GovExcelSheetName.MASTER.value,
                GovExcelSheetName.HSN_B2B.value,
                GovExcelSheetName.HSN_B2C.value,
            },
        )

    def test_v21_supeco_keeps_eco_sheet(self):
        result = self._filter_sheets("V2.1", "supeco")
        self.assertEqual(result, {GovExcelSheetName.MASTER.value, GovExcelSheetName.SUPECOM.value})

    def test_multi_section_keeps_all_selected_sheets(self):
        result = self._filter_sheets("V2.1", ["b2b", "cdnr"])
        self.assertEqual(
            result,
            {GovExcelSheetName.MASTER.value, GovExcelSheetName.B2B.value, GovExcelSheetName.CDNR.value},
        )

    def test_multi_section_with_hsn_bifurcation(self):
        result = self._filter_sheets("V2.1", ["b2b", "hsn"])
        self.assertEqual(
            result,
            {
                GovExcelSheetName.MASTER.value,
                GovExcelSheetName.B2B.value,
                GovExcelSheetName.HSN_B2B.value,
                GovExcelSheetName.HSN_B2C.value,
            },
        )

    def test_every_section_on_both_templates_keeps_master(self):
        for template_version in ("V2.0", "V2.1"):
            for section in GOV_EXCEL_SECTIONS:
                with self.subTest(template=template_version, section=section):
                    result = self._filter_sheets(template_version, section)
                    self.assertIn(
                        GovExcelSheetName.MASTER.value,
                        result,
                    )
                    self.assertGreater(len(result), 1)

    def test_every_offered_section_can_render_headers(self):
        gov = GovExcel()
        for section in GOV_EXCEL_SECTIONS:
            # Expand to the actual data keys build_excel iterates (HSN → b2b/b2c).
            for is_bifurcated in (False, True):
                for key in _get_selected_sections(section, is_hsn_bifurcated=is_bifurcated):
                    with self.subTest(section=section, key=key, bifurcated=is_bifurcated):
                        headers = gov.get_category_headers(key)
                        self.assertTrue(headers)
