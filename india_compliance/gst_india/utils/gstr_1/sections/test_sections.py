# Copyright (c) 2024, Resilient Tech and Contributors
# See license.txt

"""Tests for the rules the category modules share.

Guards the behaviour the refactor introduced -- table-ordered keys, blanks kept while reading and
dropped only at the JSON boundary, money rounded one way only -- and proves every category can
rebuild the portal payload it was read from.

Needs a site: rounding and the party-name lookup both read site settings.
    bench --site <site> run-tests --module \
        india_compliance.gst_india.utils.gstr_1.sections.test_sections
"""

import itertools
import unittest
from typing import ClassVar

from india_compliance.gst_returns.fields.gstr1 import DocField as doc
from india_compliance.gst_returns.fields.gstr1 import ItemField as item
from india_compliance.gst_returns.fields.gstr1 import RawField as raw
from india_compliance.gst_returns.fields.gstr1 import SubCategory

from . import (
    SECTIONS,
    advances,
    b2b,
    b2cl,
    b2cs,
    cdnr,
    cdnur,
    doc_issue,
    exports,
    hsn,
    nil_rated,
    summary,
    supecom,
)
from . import _shared as s

COMPANY_GSTIN = "24AAUPV7468F1ZW"


def flatten(canonical):
    """Rows as the export sees them, once the matching keys are dropped."""
    rows = []

    for section in canonical.values():
        values = list(section.values())
        rows.extend(itertools.chain(*values) if values and isinstance(values[0], list) else values)

    return rows


class TestPick(unittest.TestCase):
    KEYS: ClassVar[dict] = {"b": "second", "a": "first"}

    def test_emits_in_table_order_not_source_order(self):
        # the portal reads key order off the table, so a source-ordered rename would change output
        self.assertEqual(list(s.pick({"a": 1, "b": 2}, self.KEYS)), ["second", "first"])

    def test_drops_keys_not_in_table(self):
        self.assertEqual(s.pick({"a": 1, "zz": 9}, self.KEYS), {"first": 1})

    def test_keeps_a_blank_the_portal_sent(self):
        # this is what makes canonical lossless: an empty value the portal sent is still data
        self.assertEqual(s.pick({"a": ""}, self.KEYS), {"first": ""})

    def test_reads_back_the_other_way(self):
        self.assertEqual(s.pick_back({"first": 1, "second": 2}, self.KEYS), {"b": 2, "a": 1})


class TestKeyTables(unittest.TestCase):
    def test_every_category_table_is_reversible(self):
        for module in (b2b, b2cl, exports, b2cs, nil_rated, cdnr, cdnur, hsn, advances, doc_issue, supecom):
            with self.subTest(module.__name__):
                s.invert(module.KEYS)

    def test_summary_table_is_not_reversible_and_does_not_have_to_be(self):
        # two portal keys become one description; the summary is never filed back
        with self.assertRaises(ValueError):
            s.invert(summary.KEYS)

    def test_every_category_is_registered(self):
        self.assertEqual(len(SECTIONS), 13)


class TestGrouping(unittest.TestCase):
    ROWS: ClassVar[list] = [
        {"customer_gstin": "A", "document_number": "1"},
        {"customer_gstin": "B", "document_number": "2"},
        {"customer_gstin": "A", "document_number": "3"},
    ]
    GROUPS: ClassVar[list] = [
        {"ctin": "A", "inv": [{"inum": "1"}, {"inum": "3"}]},
        {"ctin": "B", "inv": [{"inum": "2"}]},
    ]

    def group(self, rows):
        return s.groups_from_rows(
            rows,
            group_key=lambda row: row["customer_gstin"],
            group_header=lambda row: {"ctin": row["customer_gstin"]},
            rows_field="inv",
            write_row=lambda row: {"inum": row["document_number"]},
        )

    def ungroup(self, groups):
        return list(
            s.rows_from_groups(
                groups,
                "inv",
                lambda group: {"customer_gstin": group["ctin"]},
                lambda row, header: {**header, "document_number": row["inum"]},
            )
        )

    def test_rows_group_under_their_key(self):
        self.assertEqual(self.group(self.ROWS), self.GROUPS)

    def test_first_row_of_a_key_writes_the_header(self):
        rows = [{"customer_gstin": "A", "name": "First"}, {"customer_gstin": "A", "name": "Second"}]
        out = s.groups_from_rows(
            rows,
            group_key=lambda row: row["customer_gstin"],
            group_header=lambda row: {"ctin": row["customer_gstin"], "nm": row["name"]},
            rows_field="inv",
            write_row=lambda row: {"nm": row["name"]},
        )
        self.assertEqual(out[0]["nm"], "First")

    def test_groups_flatten_back_with_the_header_on_each_row(self):
        self.assertEqual(self.ungroup(self.GROUPS), self.ROWS[:1] + self.ROWS[2:] + self.ROWS[1:2])

    def test_a_group_with_no_rows_is_skipped(self):
        self.assertEqual(self.ungroup([{"ctin": "A"}]), [])

    def test_each_direction_undoes_the_other(self):
        back = self.ungroup(self.group(self.ROWS))
        self.assertEqual(sorted(back, key=str), sorted(self.ROWS, key=str))


class TestStripEmpty(unittest.TestCase):
    def test_drops_blanks(self):
        self.assertEqual(s.strip_empty({"a": 1, "b": None, "c": "", "d": {}, "e": []}), {"a": 1})

    def test_keeps_zero_and_false(self):
        # a zero amount is a filed amount
        self.assertEqual(s.strip_empty({"a": 0, "b": 0.0, "c": False}), {"a": 0, "b": 0.0, "c": False})

    def test_reaches_inside_lists_and_nested_rows(self):
        self.assertEqual(
            s.strip_empty({"itms": [{"txval": 1, "rt": None}]}),
            {"itms": [{"txval": 1}]},
        )

    def test_keeps_a_row_that_empties_out(self):
        # matches what the mapper used to emit: the wrapper stays, its blank contents go
        self.assertEqual(s.strip_empty({"itm_det": {"txval": ""}}), {"itm_det": {}})


class TestPlaceOfSupply(unittest.TestCase):
    def test_portal_number_becomes_the_stored_format(self):
        self.assertEqual(s.pos_from_gov("05"), "05-Uttarakhand")

    def test_stored_format_goes_back_as_a_number(self):
        self.assertEqual(s.pos_to_gov("05-Uttarakhand"), "05")

    def test_round_trips(self):
        for number in ("05", "24", "96"):
            self.assertEqual(s.pos_to_gov(s.pos_from_gov(number)), number)


class TestItemTotals(unittest.TestCase):
    def test_item_amounts_pair_with_prefixed_invoice_totals(self):
        # replaces building the name with f"total_{field}", which produced total_total_* for advances
        for line, total in s.ITEM_TOTALS.items():
            self.assertEqual(total, f"total_{line}")

    def test_accumulates_rather_than_resets(self):
        row = {}
        items = [{item.TAXABLE_VALUE: 100}, {item.TAXABLE_VALUE: 50}]
        s.add_item_totals(row, items, s.ITEM_TOTALS)
        s.add_item_totals(row, items, s.ITEM_TOTALS)
        self.assertEqual(row[doc.TAXABLE_VALUE], 300)

    def test_tolerates_no_items(self):
        self.assertEqual(s.add_item_totals({}, None, s.ITEM_TOTALS), {})


class TestMoney(unittest.TestCase):
    RAW: ClassVar[list] = [
        {
            raw.CUST_GSTIN: "24AANFA2641L1ZF",
            raw.INVOICES: [
                {
                    raw.DOC_NUMBER: "S1",
                    raw.DOC_DATE: "24-11-2016",
                    raw.DOC_VALUE: 729248.164,
                    raw.POS: "06",
                    raw.REVERSE_CHARGE: "N",
                    raw.INVOICE_TYPE: "R",
                    raw.ITEMS: [
                        {raw.INDEX: 1, raw.ITEM_DETAILS: {raw.TAX_RATE: 5, raw.TAXABLE_VALUE: 10.006}}
                    ],
                }
            ],
        }
    ]

    def test_reading_does_not_round(self):
        row = flatten(b2b.to_canonical(self.RAW))[0]
        self.assertEqual(row[doc.DOC_VALUE], 729248.164)
        self.assertEqual(row[doc.ITEMS][0][item.TAXABLE_VALUE], 10.006)

    def test_writing_rounds(self):
        rows = flatten(b2b.to_canonical(self.RAW))
        out = b2b.to_gov(rows)[0][raw.INVOICES][0]
        self.assertEqual(out[raw.DOC_VALUE], 729248.16)
        self.assertEqual(out[raw.ITEMS][0][raw.ITEM_DETAILS][raw.TAXABLE_VALUE], 10.01)


class TestFlag(unittest.TestCase):
    ROW: ClassVar[dict] = {
        doc.CUST_GSTIN: "24AANFA2641L1ZF",
        doc.DOC_NUMBER: "S1",
        doc.DOC_DATE: "2016-11-24",
        doc.POS: "06-Haryana",
        doc.ITEMS: [{item.TAX_RATE: 5, item.TAXABLE_VALUE: 100}],
    }

    def test_never_reaches_canonical(self):
        raw_data = [
            {
                raw.CUST_GSTIN: "24AANFA2641L1ZF",
                raw.INVOICES: [{**TestMoney.RAW[0][raw.INVOICES][0], raw.FLAG: "D"}],
            }
        ]
        self.assertNotIn(doc.FLAG, flatten(b2b.to_canonical(raw_data))[0])

    def test_survives_to_the_portal_when_the_export_sets_it(self):
        out = b2b.to_gov([{**self.ROW, doc.FLAG: "D"}])[0][raw.INVOICES][0]
        self.assertEqual(out[raw.FLAG], "D")

    def test_absent_when_not_set(self):
        self.assertNotIn(raw.FLAG, b2b.to_gov([dict(self.ROW)])[0][raw.INVOICES][0])


class TestCreditNoteSigns(unittest.TestCase):
    RAW: ClassVar[list] = [
        {
            raw.CUST_GSTIN: "24AANFA2641L1ZF",
            raw.NOTE_DETAILS: [
                {
                    raw.NOTE_TYPE: "C",
                    raw.NOTE_NUMBER: "533515",
                    raw.NOTE_DATE: "23-09-2016",
                    raw.POS: "03",
                    raw.REVERSE_CHARGE: "Y",
                    raw.INVOICE_TYPE: "DE",
                    raw.DOC_VALUE: 123123,
                    raw.ITEMS: [
                        {raw.INDEX: 1, raw.ITEM_DETAILS: {raw.TAX_RATE: 10, raw.TAXABLE_VALUE: 5225.28}}
                    ],
                }
            ],
        }
    ]

    def test_stored_negative(self):
        row = flatten(cdnr.to_canonical(self.RAW))[0]
        self.assertEqual(row[doc.DOC_VALUE], -123123)
        self.assertEqual(row[doc.ITEMS][0][item.TAXABLE_VALUE], -5225.28)
        self.assertEqual(row[doc.TAXABLE_VALUE], -5225.28)

    def test_filed_unsigned(self):
        out = cdnr.to_gov(flatten(cdnr.to_canonical(self.RAW)))[0][raw.NOTE_DETAILS][0]
        self.assertEqual(out[raw.DOC_VALUE], 123123)
        self.assertEqual(out[raw.ITEMS][0][raw.ITEM_DETAILS][raw.TAXABLE_VALUE], 5225.28)

    def test_debit_note_stays_positive(self):
        payload = [
            {
                raw.CUST_GSTIN: "24AANFA2641L1ZF",
                raw.NOTE_DETAILS: [{**self.RAW[0][raw.NOTE_DETAILS][0], raw.NOTE_TYPE: "D"}],
            }
        ]
        self.assertEqual(flatten(cdnr.to_canonical(payload))[0][doc.DOC_VALUE], 123123)


# one realistic portal payload per category, used by the round-trip and zero-difference tests
PAYLOADS = {
    "b2b": (b2b.to_canonical, b2b.to_gov, TestMoney.RAW),
    "cdnr": (cdnr.to_canonical, cdnr.to_gov, TestCreditNoteSigns.RAW),
    "b2cl": (
        b2cl.to_canonical,
        b2cl.to_gov,
        [
            {
                raw.POS: "05",
                raw.INVOICES: [
                    {
                        raw.DOC_NUMBER: "92661",
                        raw.DOC_DATE: "10-01-2016",
                        raw.DOC_VALUE: 784586.33,
                        raw.ITEMS: [
                            {
                                raw.INDEX: 1,
                                raw.ITEM_DETAILS: {
                                    raw.TAX_RATE: 5,
                                    raw.TAXABLE_VALUE: 10000,
                                    raw.IGST: 833.33,
                                },
                            }
                        ],
                    }
                ],
            }
        ],
    ),
    "exports": (
        exports.to_canonical,
        exports.to_gov,
        [
            {
                raw.EXPORT_TYPE: "WPAY",
                raw.INVOICES: [
                    {
                        raw.DOC_NUMBER: "81542",
                        raw.DOC_DATE: "12-02-2016",
                        raw.DOC_VALUE: 995048.36,
                        raw.SHIPPING_PORT_CODE: "013027",
                        raw.SHIPPING_BILL_NUMBER: "7896542",
                        raw.SHIPPING_BILL_DATE: "04-10-2016",
                        raw.ITEMS: [{raw.TAX_RATE: 5, raw.TAXABLE_VALUE: 10000, raw.IGST: 833.33}],
                    }
                ],
            }
        ],
    ),
    # supply type is derived on write, so the payload already carries the portal's value
    "b2cs": (
        b2cs.to_canonical,
        b2cs.to_gov,
        [
            {
                raw.TAXABLE_VALUE: 110,
                raw.TYPE: "OE",
                raw.POS: "05",
                raw.TAX_RATE: 5,
                raw.IGST: 10,
                raw.SUPPLY_TYPE: "INTER",
            }
        ],
    ),
    "nil_rated": (
        nil_rated.to_canonical,
        nil_rated.to_gov,
        {
            raw.INVOICES: [
                {
                    raw.SUPPLY_TYPE: "INTRB2B",
                    raw.EXEMPTED_AMOUNT: 123.45,
                    raw.NIL_RATED_AMOUNT: 1470.85,
                    raw.NON_GST_AMOUNT: 1258.5,
                }
            ]
        },
    ),
    "cdnur": (
        cdnur.to_canonical,
        cdnur.to_gov,
        [
            {
                raw.TYPE: "B2CL",
                raw.NOTE_TYPE: "C",
                raw.NOTE_NUMBER: "533515",
                raw.NOTE_DATE: "23-09-2016",
                raw.DOC_VALUE: 123123,
                raw.POS: "03",
                raw.ITEMS: [
                    {
                        raw.INDEX: 1,
                        raw.ITEM_DETAILS: {
                            raw.TAX_RATE: 10,
                            raw.TAXABLE_VALUE: 5225.28,
                            raw.IGST: 339.64,
                        },
                    }
                ],
            }
        ],
    ),
    "hsn": (
        hsn.to_canonical,
        hsn.to_gov,
        {
            raw.HSN_B2B: [
                {
                    raw.INDEX: 1,
                    raw.HSN_CODE: "1102",
                    raw.DESCRIPTION: "CEREAL FLOURS",
                    raw.UOM: "BOX",
                    raw.QUANTITY: 2,
                    raw.TAXABLE_VALUE: 100,
                    raw.CGST: 0.5,
                    raw.SGST: 0.5,
                    raw.TAX_RATE: 1,
                }
            ]
        },
    ),
    "doc_issue": (
        doc_issue.to_canonical,
        doc_issue.to_gov,
        {
            raw.DOC_ISSUE_DETAILS: [
                {
                    raw.DOC_ISSUE_NUMBER: 1,
                    raw.DOC_ISSUE_LIST: [
                        {
                            raw.INDEX: 1,
                            raw.FROM_SR: "1",
                            raw.TO_SR: "10",
                            raw.TOTAL_COUNT: 10,
                            raw.CANCELLED_COUNT: 0,
                            raw.NET_ISSUE: 10,
                        }
                    ],
                }
            ]
        },
    ),
    "supecom": (
        supecom.to_canonical,
        supecom.to_gov,
        {
            raw.SUPECOM_52: [
                {
                    raw.ECOMMERCE_GSTIN: "20ALYPD6528PQC5",
                    raw.NET_TAXABLE_VALUE: 10000,
                    raw.ECOM_IGST: 1000,
                    raw.ECOM_CGST: 0,
                    raw.ECOM_SGST: 0,
                    raw.ECOM_CESS: 0,
                }
            ]
        },
    ),
    "advances_received": (
        advances.received_to_canonical,
        advances.received_to_gov,
        [
            {
                raw.POS: "05",
                raw.SUPPLY_TYPE: "INTER",
                raw.ITEMS: [
                    {
                        raw.IGST: 5,
                        raw.CESS: 0,
                        raw.CGST: 0,
                        raw.SGST: 0,
                        raw.ADVANCE_AMOUNT: 100,
                        raw.TAX_RATE: 5,
                    }
                ],
            }
        ],
    ),
    "advances_adjusted": (
        advances.adjusted_to_canonical,
        advances.adjusted_to_gov,
        [
            {
                raw.POS: "05",
                raw.SUPPLY_TYPE: "INTER",
                raw.ITEMS: [
                    {
                        raw.IGST: 5,
                        raw.CESS: 0,
                        raw.CGST: 0,
                        raw.SGST: 0,
                        raw.ADVANCE_AMOUNT: 100,
                        raw.TAX_RATE: 5,
                    }
                ],
            }
        ],
    ),
}


def rebuild(reader, writer, payload):
    """What the portal would receive: mapped back, then blanks dropped as the boundary does."""
    return s.strip_empty(writer(flatten(reader(payload)), company_gstin=COMPANY_GSTIN))


class TestRoundTrip(unittest.TestCase):
    """Everything the portal sent must survive raw -> canonical -> raw, for every category.

    Nothing is dropped while reading any more, so no field can go missing. Two differences are
    allowed and both are additions, not losses: amounts are rounded to the two decimals the portal
    accepts, and every item line is filled out with zeros for the amounts it did not carry.
    """

    def survives(self, sent, back, path="root"):
        if isinstance(sent, dict):
            for key, value in sent.items():
                self.assertIn(key, back, f"{path}.{key} was lost")
                self.survives(value, back[key], f"{path}.{key}")

        elif isinstance(sent, list):
            self.assertEqual(len(sent), len(back), f"{path} changed length")
            for index, (value, other) in enumerate(zip(sent, back, strict=True)):
                self.survives(value, other, f"{path}[{index}]")

        elif isinstance(sent, float):
            self.assertAlmostEqual(sent, back, places=2, msg=path)

        else:
            self.assertEqual(sent, back, path)

    def test_every_category(self):
        for name, (reader, writer, payload) in PAYLOADS.items():
            with self.subTest(name):
                self.survives(payload, rebuild(reader, writer, payload))

    def test_adjusted_advances_are_stored_negative(self):
        rows = flatten(advances.adjusted_to_canonical(PAYLOADS["advances_adjusted"][2]))
        self.assertEqual(rows[0][doc.TAXABLE_VALUE], -100)


class TestZeroDifference(unittest.TestCase):
    """A zero rate difference must not reach the portal, which rejects it.

    The old engine dropped it once for every category; now each writer says so itself, so this
    checks all of them rather than trusting one.
    """

    def test_dropped_by_every_category_that_maps_it(self):
        for name, (reader, writer, payload) in PAYLOADS.items():
            module = SECTIONS_BY_NAME[name]
            if raw.DIFF_PERCENTAGE not in module.KEYS:
                continue

            with self.subTest(name):
                rows = flatten(reader(payload))
                for row in rows:
                    row[doc.DIFF_PERCENTAGE] = 0

                emitted = s.strip_empty(writer(rows, company_gstin=COMPANY_GSTIN))
                self.assertNotIn(raw.DIFF_PERCENTAGE, str(emitted))


SECTIONS_BY_NAME = {
    "b2b": b2b,
    "b2cl": b2cl,
    "exports": exports,
    "b2cs": b2cs,
    "nil_rated": nil_rated,
    "cdnr": cdnr,
    "cdnur": cdnur,
    "hsn": hsn,
    "doc_issue": doc_issue,
    "supecom": supecom,
    "advances_received": advances,
    "advances_adjusted": advances,
}


class TestSummary(unittest.TestCase):
    RAW: ClassVar[list] = [
        {"sec_nm": "B2B", "ttl_rec": 2, "ttl_tax": 5000, "ttl_igst": 900},
        {"sec_nm": "B2B_4A", "ttl_rec": 2, "ttl_tax": 5000, "ttl_igst": 900},
        {"sec_nm": "DOC_ISSUE", "ttl_rec": 9, "net_doc_issued": 7, "ttl_doc_issued": 9},
    ]

    def test_section_codes_become_names(self):
        rows = summary.to_canonical(self.RAW)["summary"]
        self.assertIn("B2B, SEZ, DE", rows)
        self.assertEqual(rows["B2B Regular"][doc.DESCRIPTION], SubCategory.B2B_REGULAR.value)

    def test_document_ranges_count_what_was_issued(self):
        rows = summary.to_canonical(self.RAW)["summary"]
        self.assertEqual(rows["Document Issued"]["no_of_records"], 7)

    def test_overview_indents_subcategories_under_their_category(self):
        rows = list(summary.to_canonical(self.RAW[:2])["summary"].values())
        overview = summary.to_overview(rows)
        self.assertEqual([row["indent"] for row in overview], [0, 1])
        self.assertEqual(overview[0][doc.DESCRIPTION], "B2B, SEZ, DE")
        self.assertEqual(overview[1][doc.DESCRIPTION], SubCategory.B2B_REGULAR.value)

    def test_amendments_collapse_into_one_closing_line(self):
        rows = [
            {doc.DESCRIPTION: "B2B, SEZ, DE", doc.TAXABLE_VALUE: 5000},
            {doc.DESCRIPTION: "B2B, SEZ, DE (Amended)", doc.TAXABLE_VALUE: 250},
        ]
        overview = summary.to_overview(rows)
        self.assertEqual(overview[-1][doc.DESCRIPTION], "Net Liability from Amendments")
        self.assertEqual(overview[-1][doc.TAXABLE_VALUE], 250)


if __name__ == "__main__":
    unittest.main()
