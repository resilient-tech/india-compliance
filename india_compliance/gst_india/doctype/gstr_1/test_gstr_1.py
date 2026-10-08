# Copyright (c) 2024, Resilient Tech and Contributors
# See license.txt

import frappe
from erpnext.controllers.sales_and_purchase_return import make_return_doc
from frappe.tests import IntegrationTestCase, change_settings
from frappe.utils import flt, getdate

from india_compliance.gst_india.api_classes.taxpayer_returns import GSTR1API
from india_compliance.gst_india.doctype.gstr_1.gstr_1 import (
    get_journal_entries,
    make_journal_entry,
)
from india_compliance.gst_india.doctype.gstr_1.gstr_1_export import (
    GovExcel,
    _filter_data_by_sections,
    _get_excel_sheet_names,
    _get_gov_filename,
    _get_selected_sections,
)
from india_compliance.gst_india.utils import MONTHS
from india_compliance.gst_india.utils.exporter import ExcelExporter
from india_compliance.gst_india.utils.gstr_1 import (
    JSON_CATEGORY_EXCEL_CATEGORY_MAPPING,
    JsonKey,
    SheetName,
)
from india_compliance.gst_india.utils.tests import create_sales_invoice

# Every JsonKey value that maps to a sheet in JSON_CATEGORY_EXCEL_CATEGORY_MAPPING.
# sec_sum is excluded (no sheet mapping). Used for exhaustive template checks.
GOV_EXCEL_SECTIONS = frozenset(
    key.value for key in JsonKey if key.value in JSON_CATEGORY_EXCEL_CATEGORY_MAPPING
)


class TestGSTR1(IntegrationTestCase):
    company = "_Test Indian Registered Company"
    company_gstin = "24AAQCA8719H1ZC"

    def setUp(self):
        for doctype in ("Sales Invoice", "Journal Entry"):
            frappe.db.delete(doctype, filters={"company": self.company})

        today = getdate()
        self.month_or_quarter = MONTHS[today.month - 1]
        self.year = str(today.year)

    def get_journal_entry_rows(self):
        je_details = get_journal_entries(self.month_or_quarter, self.year, self.company, "Monthly")
        return (je_details or {}).get("data") or []

    def create_reverse_charge_invoice(self, qty=2, rate=1000):
        return create_sales_invoice(
            customer="_Test Registered Customer",
            item_code="_Test Trading Goods 1",
            qty=qty,
            rate=rate,
            is_reverse_charge=1,
            is_in_state_rcm=1,
        )

    @change_settings("GST Settings", {"enable_reverse_charge_in_sales": 1})
    def test_partial_credit_note_nets_against_invoice(self):
        """An RCM invoice and a partial credit note land on the same account_head with opposite
        signs. The suggested JE must net them into a single debit-or-credit row, never both."""
        invoice = self.create_reverse_charge_invoice(qty=2, rate=1000)

        credit_note = make_return_doc("Sales Invoice", invoice.name)
        credit_note.items[0].qty = -1  # return half of it
        credit_note.save().submit()

        rows = self.get_journal_entry_rows()

        # 2000 taxable - 1000 returned = 1000 net @ 9%: the liability moves off the output
        # account and onto the reverse charge account, so one is debited and the other credited
        amounts = {
            row["account"]: (
                flt(row["debit_in_account_currency"]),
                flt(row["credit_in_account_currency"]),
            )
            for row in rows
        }
        self.assertEqual(amounts["Output Tax CGST - _TIRC"], (90.0, 0.0))
        self.assertEqual(amounts["Output Tax CGST RCM - _TIRC"], (0.0, 90.0))

        journal_entry = make_journal_entry(
            self.company,
            self.company_gstin,
            self.month_or_quarter,
            self.year,
            rows,
            frappe._dict(posting_date=getdate(), auto_submit=1),
        )
        self.assertTrue(journal_entry)
        self.assertEqual(frappe.db.get_value("Journal Entry", journal_entry, "docstatus"), 1)

    @change_settings("GST Settings", {"enable_reverse_charge_in_sales": 1})
    def test_fully_reversed_invoice_suggests_nothing(self):
        """A credit note that fully reverses the invoice nets to zero — there is no liability to
        adjust, and a 0/0 row would be rejected by Journal Entry."""
        invoice = self.create_reverse_charge_invoice()

        credit_note = make_return_doc("Sales Invoice", invoice.name)
        credit_note.save().submit()

        rows = self.get_journal_entry_rows()
        self.assertEqual(rows, [])


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
        self.assertEqual(_get_selected_sections(JsonKey.HSN.value, is_hsn_bifurcated=False), ["hsn"])

    def test_hsn_post_bifurcation_returns_split_keys(self):
        self.assertEqual(
            _get_selected_sections(JsonKey.HSN.value, is_hsn_bifurcated=True),
            ["hsn_b2b", "hsn_b2c"],
        )

    def test_unknown_section_is_returned_as_is(self):
        self.assertEqual(_get_selected_sections("nonexistent", is_hsn_bifurcated=False), ["nonexistent"])

    def test_non_hsn_section_returns_single_sheet(self):
        self.assertEqual(
            _get_excel_sheet_names(_get_selected_sections("b2b", is_hsn_bifurcated=False)),
            [SheetName.B2B.value],
        )

    def test_hsn_pre_bifurcation_returns_single_sheet(self):
        self.assertEqual(
            _get_excel_sheet_names(_get_selected_sections(JsonKey.HSN.value, is_hsn_bifurcated=False)),
            [SheetName.HSN.value],
        )

    def test_hsn_post_bifurcation_returns_both_split_sheets(self):
        self.assertEqual(
            _get_excel_sheet_names(_get_selected_sections(JsonKey.HSN.value, is_hsn_bifurcated=True)),
            [SheetName.HSN_B2B.value, SheetName.HSN_B2C.value],
        )

    def test_supeco_resolves_to_eco_sheet(self):
        self.assertEqual(
            _get_excel_sheet_names(_get_selected_sections(JsonKey.SUPECOM.value, is_hsn_bifurcated=False)),
            [SheetName.SUPECOM.value],
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
        self.assertEqual(result, {SheetName.MASTER.value, SheetName.B2B.value})

    def test_v20_hsn_keeps_single_hsn_sheet(self):
        result = self._filter_sheets("V2.0", "hsn")
        self.assertEqual(result, {SheetName.MASTER.value, SheetName.HSN.value})

    def test_v21_hsn_keeps_both_bifurcated_sheets(self):
        result = self._filter_sheets("V2.1", "hsn")
        self.assertEqual(
            result,
            {
                SheetName.MASTER.value,
                SheetName.HSN_B2B.value,
                SheetName.HSN_B2C.value,
            },
        )

    def test_v21_supeco_keeps_eco_sheet(self):
        result = self._filter_sheets("V2.1", "supeco")
        self.assertEqual(result, {SheetName.MASTER.value, SheetName.SUPECOM.value})

    def test_multi_section_keeps_all_selected_sheets(self):
        result = self._filter_sheets("V2.1", ["b2b", "cdnr"])
        self.assertEqual(
            result,
            {SheetName.MASTER.value, SheetName.B2B.value, SheetName.CDNR.value},
        )

    def test_multi_section_with_hsn_bifurcation(self):
        result = self._filter_sheets("V2.1", ["b2b", "hsn"])
        self.assertEqual(
            result,
            {
                SheetName.MASTER.value,
                SheetName.B2B.value,
                SheetName.HSN_B2B.value,
                SheetName.HSN_B2C.value,
            },
        )

    def test_every_section_on_both_templates_keeps_master(self):
        for template_version in ("V2.0", "V2.1"):
            for section in GOV_EXCEL_SECTIONS:
                with self.subTest(template=template_version, section=section):
                    result = self._filter_sheets(template_version, section)
                    self.assertIn(
                        SheetName.MASTER.value,
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
