# Copyright (c) 2024, Resilient Tech and Contributors
# See license.txt

from frappe.tests import IntegrationTestCase

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
        self.assertIn("b2b", result)
        self.assertIn("cdnr", result)

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
            [GovExcelSheetName.ECO.value],
        )

    def test_unknown_section_returns_empty_list(self):
        self.assertEqual(
            _get_excel_sheet_names(_get_selected_sections("nonexistent", is_hsn_bifurcated=False)), []
        )

    def test_includes_section_name_when_section_given(self):
        filename = _get_gov_filename(self.GSTIN, self.PERIOD, "b2b")
        self.assertEqual(filename, f"GSTR-1-Gov-{self.GSTIN}-{self.PERIOD}-b2b")

    def test_default_filename_when_no_section(self):
        filename = _get_gov_filename(self.GSTIN, self.PERIOD, None)
        self.assertEqual(filename, f"GSTR-1-Gov-{self.GSTIN}-{self.PERIOD}")

    def test_default_filename_when_section_omitted(self):
        filename = _get_gov_filename(self.GSTIN, self.PERIOD)
        self.assertEqual(filename, f"GSTR-1-Gov-{self.GSTIN}-{self.PERIOD}")

    def _filter_sheets(self, template_version, section):
        is_hsn_bifurcated = template_version == "V2.1"
        sheet_names = _get_excel_sheet_names(_get_selected_sections(section, is_hsn_bifurcated))
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
        self.assertEqual(result, {GovExcelSheetName.MASTER.value, GovExcelSheetName.ECO.value})

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
